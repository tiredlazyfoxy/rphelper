// Feature 022, step 003 — the pure think-segment parser (DoD-1..3).
//
// Expected values come from context.md D4 (the rule text and its worked-examples table,
// rows 1–10) and from the step file's DoD-2 (021 D4's stripped outputs). Never from code.
import { describe, expect, it } from "vitest";
import { splitThinking, type ThinkingSegment } from "../../src/app/thinking";

function answer(text: string): ThinkingSegment {
  return { kind: "answer", text };
}

function think(text: string, closed: boolean): ThinkingSegment {
  return { kind: "think", text, closed };
}

/** The answer segments' texts, in order. */
function answerTexts(segments: ThinkingSegment[]): string[] {
  return segments.filter((s) => s.kind === "answer").map((s) => s.text);
}

// ---------------------------------------------------------------------------
describe("splitThinking — D4 worked examples", () => {
  const rows: Array<{ row: number; input: string; expected: ThinkingSegment[] }> = [
    { row: 1, input: "Hello", expected: [answer("Hello")] },
    { row: 2, input: "  Hello  ", expected: [answer("  Hello  ")] },
    {
      row: 3,
      input: "<think>plan</think>\n\nHello",
      expected: [think("plan", true), answer("Hello")],
    },
    {
      row: 4,
      input: "<think>a</think>One<think>b</think> two",
      expected: [think("a", true), answer("One"), think("b", true), answer("two")],
    },
    {
      row: 5,
      input: "Start<think>never closed",
      expected: [answer("Start"), think("never closed", false)],
    },
    { row: 6, input: "<think>only</think>", expected: [think("only", true)] },
    { row: 7, input: "a </think> b", expected: [answer("a </think> b")] },
    {
      row: 8,
      input: "<think>x\ny</think>\n((ooc))",
      expected: [think("x\ny", true), answer("((ooc))")],
    },
    { row: 9, input: "<think>", expected: [think("", false)] },
    { row: 10, input: "", expected: [answer("")] },
  ];

  for (const { row, input, expected } of rows) {
    it(`row ${row}: ${JSON.stringify(input)} splits into exactly the listed segments, in order — DoD-1`, () => {
      expect(splitThinking(input)).toEqual(expected);
    });
  }

  it("row 8's think text is exactly x, newline, y — never trimmed — DoD-1", () => {
    const segments = splitThinking("<think>x\ny</think>\n((ooc))");
    const thinks = segments.filter((s) => s.kind === "think");
    expect(thinks.map((s) => s.text)).toEqual(["x\ny"]);
  });

  it("row 2 keeps the input byte-for-byte when no think block is found — DoD-1", () => {
    const segments = splitThinking("  Hello  ");
    expect(segments).toHaveLength(1);
    expect(segments[0]).toEqual({ kind: "answer", text: "  Hello  " });
  });
});

// ---------------------------------------------------------------------------
describe("splitThinking — consistent with 021 D4's strip rule", () => {
  it("row 3: the answer segments joined with a space equal Hello — DoD-2", () => {
    expect(answerTexts(splitThinking("<think>plan</think>\n\nHello")).join(" ")).toBe("Hello");
  });

  it("row 4: the answer segments joined with a space equal One two — DoD-2", () => {
    expect(
      answerTexts(splitThinking("<think>a</think>One<think>b</think> two")).join(" "),
    ).toBe("One two");
  });

  it("row 6: there is no answer segment, so the joined answer is empty — DoD-2", () => {
    const answers = answerTexts(splitThinking("<think>only</think>"));
    expect(answers).toEqual([]);
    expect(answers.join(" ")).toBe("");
  });

  it("row 8: the answer segments joined with a space equal ((ooc)) — DoD-2", () => {
    expect(answerTexts(splitThinking("<think>x\ny</think>\n((ooc))")).join(" ")).toBe("((ooc))");
  });

  it("row 5: the answer segments alone equal Start — DoD-2", () => {
    expect(answerTexts(splitThinking("Start<think>never closed")).join(" ")).toBe("Start");
  });
});

// ---------------------------------------------------------------------------
describe("splitThinking — the tags are case-sensitive", () => {
  it("uppercase <THINK>loud</THINK> is one answer segment with the text unchanged — DoD-3", () => {
    expect(splitThinking("<THINK>loud</THINK>")).toEqual([answer("<THINK>loud</THINK>")]);
  });
});
