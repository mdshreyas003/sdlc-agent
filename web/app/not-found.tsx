import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto flex h-full max-w-[520px] flex-col justify-center gap-3 px-6">
      <h1 className="text-[20px] font-semibold">That page does not exist</h1>
      <p className="text-[13px] text-mute">The link may be old, or the workspace may have been deleted.</p>
      <p className="flex gap-4 text-[13px]">
        <Link href="/workspaces" className="text-accent underline underline-offset-2">Your workspaces</Link>
        <Link href="/" className="text-accent underline underline-offset-2">Home</Link>
      </p>
    </div>
  );
}
