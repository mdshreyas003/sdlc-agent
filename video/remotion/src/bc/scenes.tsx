import React from "react";
import { BCScene, Slide } from "./engine";

const S = (slides: Slide[]): React.FC => () => <BCScene slides={slides} />;
const S03 = "03-incident-cluster-before.jpg";
const S04 = "04-incident-cluster-after-stage1.jpg";

export const BC1 = S([
  { k: "big", lines: ["Your code has", "rules nobody", "remembers."], w: 14 },
  { k: "type", text: "max_attempts = 3", sub: "Why 3? Nobody knows.", w: 14 },
  { k: "big", lines: ["The person who knew", "has left."], w: 10 },
]);

export const BC2 = S([
  { k: "big", lines: ["A new engineer.", "Or an AI agent."], w: 12 },
  { k: "type", text: "Try a payment at most 3 times.", w: 10 },
  { k: "big", lines: ["Looks too low.", "Raise it."], w: 8 },
  { k: "big", lines: ["The reason is gone."], w: 8 },
  { k: "big", lines: ["Hours lost."], dim: ["Tickets. Team chat. Pull requests."], w: 14 },
]);

export const BC3 = S([
  { k: "big", lines: ["Brightcart"], dim: ["A simulated online store."], w: 12 },
  { k: "shot", src: S03, cap: "214 customers charged twice.", w: 14 },
  { k: "big", lines: ["The team sets a limit."], w: 6 },
  { k: "big", lines: ["3"], size: 360, dim: ["Now the reason has a home."], w: 8 },
]);

export const BC4 = S([
  { k: "big", lines: ["What we built."], w: 6 },
  { k: "list", items: ["1  Connect your tools", "2  Sync", "3  We build a connected map", "4  Ask why. Get quotes.", "5  A person approves a decision note", "6  Agents read it before they edit"], w: 40, size: 60 },
  { k: "big", lines: ["A decision note:"], dim: ["what the team chose, and why."], w: 10 },
]);

export const BC5 = S([
  { k: "big", lines: ["One click."], dim: ["A demo workspace."], w: 9 },
  { k: "list", items: ["GitHub", "Jira", "Team chat"], head: "Or connect your tools.", w: 10 },
  { k: "big", lines: ["Test the connection."], w: 5 },
  { k: "shot", src: "08-sync.jpg", cap: "Sync.", w: 8 },
  { k: "shot", src: "09-ingestion.jpg", cap: "A live timeline for each source.", w: 8 },
  { k: "big", lines: ["A log shows every step."], w: 5 },
]);

export const BC6 = S([
  { k: "big", lines: ["Now ask why."], w: 6 },
  { k: "list", items: ["Click a line of code.", "See who changed it.", "See the ticket.", "See the chat."], w: 20 },
  { k: "shot", src: "10-blame.jpg", cap: "Who, which ticket, which chat.", w: 12 },
  { k: "big", lines: ["Every claim has", "an exact quote."], dim: ["Code checks the quote."], w: 18 },
  { k: "big", lines: ["No proof?", "Not established."], w: 14 },
]);

export const BC7 = S([
  { k: "list", items: ["Draft", "A person approves", "Agents read it"], head: "A decision note has a life.", w: 22 },
  { k: "shot", src: "01-overview.jpg", cap: "People review. Agents read.", w: 10 },
  { k: "big", lines: ["A later pull request", "updates it."], w: 8 },
  { k: "shot", src: "05-staged-update-and-source-changed.jpg", cap: "It waits for review. The old version stays live.", w: 16 },
  { k: "shot", src: "06-retired-decision-replaced.jpg", cap: "A newer decision retires the old one. With the reason.", w: 16 },
]);

export const BC8 = S([
  { k: "big", lines: ["A coding agent", "opens a pull request."], w: 10 },
  { k: "big", lines: ["Raise the limit", "from 3 to 8."], size: 130, w: 10 },
  { k: "big", lines: ["Before it edits,", "it asks memory."], w: 10 },
  {
    k: "card",
    head: "3 approved notes apply.",
    lines: ["rule     Changes to payment attempts need a reliability review", "decision Try a card payment at most 3 times", "rule     Every payment carries a unique payment ID"],
    w: 30,
  },
  { k: "big", lines: ["The agent knows what", "it would undo."], w: 8 },
]);

export const BC9 = S([
  { k: "big", lines: ["The map keeps up."], dim: ["A new chat thread joins it."], w: 10 },
  { k: "shot", src: S03, cap: "Before: 36 records. 63 links.", w: 10 },
  { k: "shot", src: S04, cap: "After: 40 records. 69 links.", w: 10 },
  { k: "big", lines: ["Two days later,", "a ticket is corrected."], w: 10 },
  { k: "shot", src: "05-staged-update-and-source-changed.jpg", cap: "Every note that cites it: source changed.", w: 12 },
  { k: "big", lines: ["A person checks it."], dim: ["Nothing goes stale in silence."], w: 8 },
]);

export const BC10 = S([
  { k: "big", lines: ["Who is this for?"], w: 5 },
  {
    k: "list",
    items: ["Engineering managers: see why", "Platform teams: roll out agents", "Security and compliance: get proof", "Support leads: know why a rule exists", "New engineers: learn fast"],
    w: 38,
    size: 56,
  },
  { k: "stats", items: [["1,999 rupees", "per repo, per month"]], head: "The price", w: 8 },
  { k: "big", lines: ["Agents are never seats."], w: 8 },
]);

export const BC11 = S([
  { k: "stats", head: "Real Kafka data", items: [["1,201", "items"], ["2,194", "links"]], w: 12 },
  { k: "stats", head: "18 questions. No model.", items: [["1", "plain search"], ["9", "connected map"]], w: 22 },
  { k: "stats", head: "Real model. First check.", items: [["5 of 7", "cases pass"]], w: 12 },
  { k: "big", lines: ["75 gold questions."], dim: ["Not checked by people yet.", "So: no accuracy number."], w: 18 },
  { k: "stats", items: [["366", "tests pass"]], w: 6 },
  { k: "list", items: ["No proof: Not established.", "Every quote checked word for word.", "Nothing goes live without a person."], w: 18, size: 58 },
  { k: "list", items: ["A changed source is flagged.", "The shared demo is read-only.", "Agent tools are read-only."], w: 12, size: 58 },
]);

export const BC12 = S([
  { k: "big", lines: ["Memory your team can check.", "And your agents can obey."], size: 100, w: 18 },
  { k: "list", items: ["Agents write.", "We guard and remember.", "Memory feeds the next agent."], head: "A software factory.", w: 22 },
  { k: "big", lines: ["Memory your team can check."], dim: ["Brightcart is simulated. The idea is real."], size: 90, w: 10 },
]);
