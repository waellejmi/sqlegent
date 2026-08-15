from src.eval.harness import execution_accuracy_official, soft_f1


def test_soft_f1_readme_example():
    gold = [("Apple", 325), ("Orange", None), ("Banana", 119)]
    pred = [(325, "Apple"), (191, "Orange"), (None, "Banana")]
    res = soft_f1(pred, gold)
    # Expected based on positional algorithm in harness:
    # tp = 2.0, fp = 1.0, fn = 1.0 -> precision = recall = 2/3 -> 0.6667
    assert round(res["precision"], 4) == 0.6667
    assert round(res["recall"], 4) == 0.6667
    assert round(res["f1"], 4) == 0.6667


def test_soft_f1_bond_case():
    gold = [("-",)]
    pred = [("-", 16), ("=", 1)]
    res = soft_f1(pred, gold)
    # Expected: precision = 1/(1+2) = 0.3333, recall = 1/(1+0) = 1.0, f1 = 0.5
    assert round(res["precision"], 4) == 0.3333
    assert round(res["recall"], 4) == 1.0
    assert round(res["f1"], 4) == 0.5


def test_execution_accuracy_official():
    # exact set equality
    gold = [(1, 2), (3, 4)]
    pred_ok = [(3, 4), (1, 2)]
    pred_bad = [(1, 2), (3, 5)]
    assert execution_accuracy_official(pred_ok, gold) == 1
    assert execution_accuracy_official(pred_bad, gold) == 0
