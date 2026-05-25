def mock_should_confirm(text):
    lower = text.lower()
    
    # Precise match logic
    should_confirm = (
        "이대로" in lower or
        "좋아" in lower or
        "오케이" in lower or
        "진행해" in lower or
        "확정" in lower or
        lower.endswith("ok") or
        lower.endswith("ok\n") or
        lower.endswith("ok\r\n")
    )
    return should_confirm

tests_true = [
    "이대로",
    "이대로 제안",
    "이대로 제안해줘",
    "좋아",
    "오케이",
    "ok",
    "진행해",
    "확정"
]

tests_false = [
    "다시 제안해줘",
    "여러 영상 골고루 섞어서 다시 제안해줘",
    "사람 중심으로 다시 제안해줘",
    "풍경 줄여서 제안해줘",
    "더 빠르게 다시 제안해줘",
    "여러 영상 골고루"
]

print("--- Testing True Cases ---")
all_true_passed = True
for t in tests_true:
    res = mock_should_confirm(t)
    print(f"[{t}] -> {res} (Expected: True)")
    if not res:
        all_true_passed = False

print("\n--- Testing False Cases ---")
all_false_passed = True
for t in tests_false:
    res = mock_should_confirm(t)
    print(f"[{t}] -> {res} (Expected: False)")
    if res:
        all_false_passed = False

print("\n--- RESULT ---")
if all_true_passed and all_false_passed:
    print("ALL TESTS PASSED SUCCESSFULLY!")
else:
    print("SOME TESTS FAILED!")
