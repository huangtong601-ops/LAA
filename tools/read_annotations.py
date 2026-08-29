# -*- coding: utf-8 -*-
"""读取某会话的全部截图标注(含特殊标注：位置+说明)，打印结构化摘要。
用法: python tools\read_annotations.py <会话ID>
"""
import sys, json
from pathlib import Path

RECORD = Path(r"E:\LAA\MaaBoilerplate\record")


def main():
    sid = sys.argv[1] if len(sys.argv) > 1 else None
    if not sid:
        print("用法: python tools\\read_annotations.py <会话ID>"); return 1
    d = RECORD / sid
    if not d.exists():
        print("会话不存在:", sid); return 1
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    print("=== 会话", sid, "标注=", meta.get("label"), "===")
    if not (d / "annotations.json").exists():
        print("无标注"); return 0
    an = json.loads((d / "annotations.json").read_text(encoding="utf-8"))
    for step in sorted(an.keys()):
        a = an[step]
        print(f"\n[{step}] label={a.get('label','')}")
        for r in a.get("regions", []):
            print(f"   - 特殊标注 @ ({r['x']},{r['y']},{r['w']},{r['h']})  note={r.get('note','')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())