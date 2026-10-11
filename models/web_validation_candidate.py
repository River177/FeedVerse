"""Content-only cold-start model with two complementary history attentions."""
import json
import random
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F


class Model(nn.Module):
    def __init__(self, public, config):
        super().__init__()
        self.config = dict(config)
        with np.load(Path(public) / 'features.npz', allow_pickle=True) as data:
            names = data['ids'].tolist()
            vectors = np.asarray(data['vectors'], dtype=np.float32)
        names = [n.decode('utf-8') if isinstance(n, bytes) else str(n) for n in names]
        if vectors.shape != (len(names), 128):
            raise ValueError('Expected aligned 128-dimensional text features')
        self.index = {n: i + 1 for i, n in enumerate(names)}
        vectors = np.nan_to_num(vectors, nan=0.0, posinf=0.0, neginf=0.0)
        x = torch.from_numpy(np.concatenate([np.zeros((1, 128), dtype=np.float32), vectors]))
        self.register_buffer('text', F.normalize(x, dim=-1))
        self.content = nn.Sequential(nn.Linear(128, 128), nn.GELU(), nn.Dropout(0.15), nn.Linear(128, 128))
        self.attention = nn.Sequential(nn.Linear(128, 64), nn.Tanh(), nn.Linear(64, 1))
        self.prior = nn.Sequential(nn.Linear(128, 64), nn.GELU(), nn.Dropout(0.15), nn.Linear(64, 1))
        self.scales = nn.Parameter(torch.tensor([2.0, 2.0, 1.0]))
        self.attention_temperature = nn.Parameter(torch.tensor(1.0))

    def article(self, ids):
        raw = self.text[ids]
        learned = F.normalize(raw + 0.3 * self.content(raw), dim=-1)
        return learned, raw

    def tensors(self, rows, candidates):
        hlen = max(1, max((len(r['history']) for r in rows), default=0))
        clen = max(1, max((len(c) for c in candidates), default=0))
        h = torch.zeros((len(rows), hlen), dtype=torch.long)
        c = torch.zeros((len(rows), clen), dtype=torch.long)
        cmask = torch.zeros((len(rows), clen), dtype=torch.bool)
        for i, (row, cand) in enumerate(zip(rows, candidates)):
            hist = [self.index.get(str(n), 0) for n in row['history']]
            h[i, :len(hist)] = torch.tensor(hist, dtype=torch.long)
            ci = [self.index.get(str(n), 0) for n in cand]
            c[i, :len(ci)] = torch.tensor(ci, dtype=torch.long)
            cmask[i, :len(ci)] = True
        return h, c, cmask

    @staticmethod
    def masked_weights(logits, mask):
        weights = torch.softmax(logits.masked_fill(~mask, -1e4), dim=-1) * mask
        return weights / weights.sum(-1, keepdim=True).clamp_min(1e-8)

    def logits(self, rows, candidates):
        h, c, cmask = self.tensors(rows, candidates)
        hv, hr = self.article(h)
        cv, cr = self.article(c)
        hmask = h.ne(0)
        global_w = self.masked_weights(self.attention(hv).squeeze(-1), hmask)
        user = torch.einsum('bh,bhd->bd', global_w, hv)
        global_match = torch.einsum('bcd,bd->bc', cv, user)
        similarity = torch.einsum('bcd,bhd->bch', cv, hv)
        temperature = F.softplus(self.attention_temperature) + 1.0
        local_w = self.masked_weights(similarity * temperature, hmask.unsqueeze(1))
        local_match = (local_w * similarity).sum(-1)
        raw_user = (hr * hmask.unsqueeze(-1)).sum(1) / hmask.sum(1, keepdim=True).clamp_min(1)
        raw_match = torch.einsum('bcd,bd->bc', cr, raw_user)
        scales = F.softplus(self.scales)
        result = scales[0] * global_match + scales[1] * local_match + scales[2] * raw_match
        result = result + self.prior(cr).squeeze(-1)
        return result.masked_fill(~cmask, -1e4)

    def fit(self, rows, output_dir):
        rng = random.Random(self.config['seed'])
        optimizer = torch.optim.AdamW(self.parameters(), lr=0.001, weight_decay=0.01)
        for epoch in range(self.config['epochs']):
            order = list(rows)
            rng.shuffle(order)
            losses = []
            self.train()
            for start in range(0, len(order), self.config['batch_size']):
                batch = order[start:start + self.config['batch_size']]
                candidates = []
                for row in batch:
                    negatives = [n for n in row['candidates'] if n != row['positive']]
                    candidates.append([row['positive']] + rng.sample(negatives, min(4, len(negatives))))
                prediction = self.logits(batch, candidates)
                loss = F.cross_entropy(prediction, torch.zeros(len(batch), dtype=torch.long))
                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.parameters(), 5.0)
                optimizer.step()
                losses.append(float(loss.detach()))
            print(json.dumps({'epoch': epoch + 1, 'loss': float(np.mean(losses))}), flush=True)
        torch.save(self.state_dict(), Path(output_dir) / 'checkpoint.pt')

    def score(self, rows):
        self.eval()
        result = []
        with torch.no_grad():
            for row in rows:
                if not row['candidates']:
                    result.append([])
                    continue
                scores = self.logits([row], [row['candidates']])[0]
                if not torch.isfinite(scores).all():
                    raise ValueError('Nonfinite model scores')
                result.append(scores.tolist())
        return result


def build(public_path, config):
    return Model(public_path, config)
