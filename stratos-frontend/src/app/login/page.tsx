import Link from "next/link";

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-black px-4">
      <section className="w-full max-w-md rounded-2xl border border-zinc-700 bg-zinc-900 p-6">
        <h1 className="text-2xl font-semibold text-zinc-100">Login</h1>
        <p className="mt-3 text-sm leading-6 text-zinc-400">
          OAuth wiring is pending backend auth integration. Continue to app and use
          the temporary Google stub for now.
        </p>
        <Link
          href="/"
          className="mt-5 inline-flex rounded-xl bg-white px-4 py-2 text-sm font-semibold text-zinc-900"
        >
          Go to app
        </Link>
      </section>
    </main>
  );
}
