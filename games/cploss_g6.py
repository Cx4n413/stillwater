import json, chess, chess.pgn, chess.engine, re

REC = r"C:\Users\nonna\Downloads\ExperimentalChessEngine\games\g6_records.json"
PGN = r"C:\Users\nonna\Downloads\ExperimentalChessEngine\games\placement_concentrate.pgn"
SF  = r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe"

recs = json.load(open(REC))
# white_cp_after[ply]; index by ply 1..116
by_ply = {r["ply"]: r for r in recs}
startcp = 33  # from analysis

# SW is Black. cp-loss for a Black move at ply p:
#   eval_before = white_cp after ply p-1 (or startcp if p==1)
#   eval_after  = white_cp after ply p
#   loss (from Black/SW perspective) = eval_after - eval_before  (White advantage grew = SW lost ground)
rows = []
for r in recs:
    if r["mover"] != "B":
        continue
    p = r["ply"]
    before = startcp if p == 1 else by_ply[p-1]["white_cp_after"]
    after = r["white_cp_after"]
    loss = after - before  # positive = SW worsened
    mvno = (p+1)//2
    rows.append((mvno, p, r["san"], before, after, loss, r["comment"]))

rows_sorted = sorted(rows, key=lambda x: -x[5])
print("=== TOP SW (Black) cp-losses (loss = White adv increase) ===")
print("mv  ply san       beforeW afterW  loss   {comment}")
for mvno,p,san,b,a,loss,c in rows_sorted[:14]:
    print("%3d %3d %-9s %6d %6d %+6d  {%s}" % (mvno,p,san,b,a,loss,c))

print("\n=== full SW move-by-move (chronological) ===")
print("mv  ply san       beforeW afterW  loss   {comment}")
for mvno,p,san,b,a,loss,c in rows:
    flag = "  <<<" if loss>=60 else ""
    print("%3d %3d %-9s %6d %6d %+6d  {%s}%s" % (mvno,p,san,b,a,loss,c,flag))

# Turning point: first SW move after which White advantage crosses and stays > +200 (2.0)
print("\n=== eval trajectory (White cp after each SW move) ===")
for mvno,p,san,b,a,loss,c in rows:
    bar = "#"*max(0,min(40,a//10))
    print("mv%3d after %-8s W=%5d %s" % (mvno,san,a,bar))
