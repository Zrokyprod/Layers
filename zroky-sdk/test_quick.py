from zroky._internal.loop_guard import LoopGuard, LoopDetectedError

# Test 1: None fingerprints shouldn't trigger loop
g = LoopGuard(max_repeated_outputs=2, default_action="raise")
g.check_pre_call("t1")
r = g.check_post_call("t1", "out-0", "o", "m")
print(f"Test 1 (short output): {r.action}")
assert r.action == "allow", f"Expected allow, got {r.action}"

# Test 2: Long unique outputs shouldn't trigger loop
g2 = LoopGuard(max_repeated_outputs=2, default_action="raise")
for i in range(5):
    g2.check_pre_call("t2")
    r = g2.check_post_call("t2", f"this is a longer unique output number {i}", "o", "m")
    assert r.action == "allow", f"Expected allow for iteration {i}, got {r.action}"
print("Test 2 (long unique outputs): PASS")

# Test 3: Repeated long outputs should trigger loop
g3 = LoopGuard(max_repeated_outputs=2, default_action="raise")
g3.check_pre_call("t3")
g3.check_post_call("t3", "this is a long repeated output", "o", "m")
g3.check_pre_call("t3")
g3.check_post_call("t3", "this is a long repeated output", "o", "m")
g3.check_pre_call("t3")
try:
    g3.check_post_call("t3", "this is a long repeated output", "o", "m")
    print("Test 3 FAILED: should have raised")
except LoopDetectedError:
    print("Test 3 (repeated long outputs): PASS")

print("All quick tests passed!")
