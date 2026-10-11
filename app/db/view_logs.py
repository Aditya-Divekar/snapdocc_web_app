"""
Quick way to see what's in request_logs without opening a database viewer.

Run:  python -m app.db.view_logs            (last 20 requests + summary)
      python -m app.db.view_logs --all      (every request)
"""

import argparse
from app.db.models import SessionLocal, RequestLog


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="show every row, not just the last 20")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        query = db.query(RequestLog).order_by(RequestLog.timestamp.desc())
        rows = query.all() if args.all else query.limit(20).all()

        if not rows:
            print("No requests logged yet. Send the bot a photo on WhatsApp first!")
            return

        print(f"{'Time':<20}{'Phone':<18}{'Type':<8}{'Fmt':<6}{'Engine':<10}{'Conf':>6}{'Secs':>7}  Status")
        print("-" * 95)
        for r in reversed(rows):   # oldest first, easier to read top-to-bottom
            t = r.timestamp.strftime("%Y-%m-%d %H:%M")
            phone = (r.phone or "")[-14:]   # last part only, keeps the table narrow
            print(f"{t:<20}{phone:<18}{(r.doc_type or ''):<8}{(r.fmt or ''):<6}"
                  f"{(r.ocr_engine or ''):<10}{r.avg_confidence:>6.2f}{r.processing_secs:>7.1f}  {r.status}")

        # Summary stats
        total = len(rows) if args.all else query.count()
        successes = query.filter(RequestLog.status == "success").count()
        avg_conf = sum(r.avg_confidence for r in rows) / len(rows)
        avg_secs = sum(r.processing_secs for r in rows) / len(rows)

        print("-" * 95)
        print(f"Total requests logged : {total}")
        print(f"Successful            : {successes} ({100*successes/total:.0f}%)" if total else "")
        print(f"Avg confidence shown  : {avg_conf:.2f}")
        print(f"Avg processing time   : {avg_secs:.1f}s")

    finally:
        db.close()


if __name__ == "__main__":
    main()
