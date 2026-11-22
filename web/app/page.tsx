import type { Metadata } from "next";
import Landing from "@/components/Landing";

export const metadata: Metadata = {
  title: "whycode: the PR guard that remembers why",
  description: "We catch the pull request that undoes a decision, with the quote, the incident and who to ask.",
};

export default function Page() {
  return <Landing />;
}
