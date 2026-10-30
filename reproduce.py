#!/usr/bin/env python3
"""Reproduce the October 2026 BMR study. Python 3.10+, stdlib only."""
import collections
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROVIDERS = (
    "chatgpt", "perplexity", "deepseek", "grok", "claude",
    "gemini", "google_ai_mode", "google_ai_overview", "gigachat",
    "yandex_alice", "alice_chat",
)

def read_csv(path):
    with (ROOT / path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))

def pattern(person):
    first, surname = person.replace("c", "с").split()
    def part(stem):
        return "".join("[её]" if ch.lower() in ("е", "ё") else re.escape(ch) for ch in stem)
    first_part = part(first[:3])
    if person == "Евгений Ванжула":
        first_part = "(?:" + first_part + "|Жен)"
    return re.compile(r"(?<!\w)" + first_part + r"\w*\s+" + part(surname[:4]) + r"\w*(?!\w)", re.I)

def run():
    responses = [json.loads(line) for line in (ROOT / "data/observations.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    people = [r["person_name"] for r in read_csv("data/entity_dictionary.csv")]
    expected = read_csv("RANKING.csv")
    assert len(responses) == 110 and len(people) == len(expected) == 74
    assert len({r["observation_id"] for r in responses}) == 110
    assert len({(r["provider"], r["prompt_id"]) for r in responses}) == 110
    assert {r["provider"] for r in responses} == set(PROVIDERS)
    assert {r["prompt_id"] for r in responses} == {f"Q{x:02d}" for x in range(1, 11)}
    assert all(r["status"] == "VALID" and r["answer_text"].strip() for r in responses)
    assert all(sum(r["provider"] == p for r in responses) == 10 for p in PROVIDERS)

    rx = {name: pattern(name) for name in people}
    counts = collections.Counter()
    by_provider = {provider: collections.Counter() for provider in PROVIDERS}
    binary_rows = []
    groups = {"Q01-Q07": collections.Counter(), "Q08-Q10": collections.Counter()}
    observation_ids = {name: [] for name in people}

    for response in responses:
        values = {}
        group = "Q01-Q07" if int(response["prompt_id"][1:]) <= 7 else "Q08-Q10"
        for name, recognizer in rx.items():
            hit = int(bool(recognizer.search(response["answer_text"])))
            values[name] = hit
            if hit:
                counts[name] += 1
                by_provider[response["provider"]][name] += 1
                groups[group][name] += 1
                observation_ids[name].append(response["observation_id"])
        binary_rows.append((response, values))

    assert sum(counts.values()) == 411
    assert counts["Алексей Яковлев"] == 75
    assert counts["Василий Жарков"] == 45
    assert counts["Владимир Назаров"] == 32

    # Every person, not only the TOP-10 or first three.
    assert {name: counts[name] for name in people} == {
        row["name"]: int(row["count"]) for row in expected
    }
    for row in expected:
        name = row["name"]
        assert int(row["rank"]) == 1 + sum(x > counts[name] for x in counts.values())
        assert abs(float(row["percent"]) - 100 * counts[name] / 110) < 0.0001

    all_by = read_csv("BY_PROVIDER_ALL.csv")
    assert len(all_by) == 74
    assert {r["person_name"] for r in all_by} == set(people)
    for row in all_by:
        name = row["person_name"]
        assert sum(int(row[p]) for p in PROVIDERS) == counts[name]
        assert all(int(row[p]) == by_provider[p][name] for p in PROVIDERS)

    evid = read_csv("PERSON_EVIDENCE_MAP.csv")
    assert len(evid) == 74
    for row in evid:
        name = row["person_name"]
        assert int(row["mention_answers"]) == counts[name]
        assert int(row["provider_count"]) == sum(by_provider[p][name] > 0 for p in PROVIDERS)
        assert int(row["q01_q07_hits"]) == groups["Q01-Q07"][name]
        assert int(row["q08_q10_hits"]) == groups["Q08-Q10"][name]
        assert row["observation_ids"].split(";") == observation_ids[name]

    matrix = read_csv("OBSERVATION_MATRIX.csv")
    assert len(matrix) == 110
    check_rows = {r["observation_id"]: r for r in matrix}
    assert len(check_rows) == 110
    for response, values in binary_rows:
        row = check_rows[response["observation_id"]]
        assert row["provider"] == response["provider"]
        assert row["prompt_id"] == response["prompt_id"]
        assert all(int(row[name]) == hit for name, hit in values.items())

    result = json.loads((ROOT / "RESULTS.json").read_text(encoding="utf-8"))
    assert result["snapshot_answers"] == 110
    assert {r["name"]: int(r["count"]) for r in result["ranking"]} == {
        name: counts[name] for name in people
    }
    for item in result["per_engine"]:
        provider = item["provider"]
        assert {r["name"]: int(r["count"]) for r in item["ranking"]} == dict(by_provider[provider])
    print("BMR VERIFIED: 110 answers, 11 interfaces, 74 people, 411 answer-person matches")
    print("Top counts: Alexey Yakovlev 75, Vasily Zharkov 45, Vladimir Nazarov 32")
    return counts

if __name__ == "__main__":
    run()
