#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from feedverse.backend import Backend
from feedverse.mcp import serve,serve_http
import argparse
p=argparse.ArgumentParser(); p.add_argument('--root'); p.add_argument('--http',type=int); args=p.parse_args()
b=Backend(args.root) if args.root else Backend()
serve_http(b,args.http) if args.http else serve(b)
