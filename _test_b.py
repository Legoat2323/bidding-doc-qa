import sys, os
sys.path.insert(0, os.getcwd())
from loguru import logger; logger.remove()
import selfcheck as sc

q = "履约保证金什么情况下不予退还？"
print("问：", q)
ans, status, rounds = sc.answer_with_selfcheck(q, is_template=False)
print("\n状态:", status, " 轮数:", rounds)
print("答案:", ans[:300])
