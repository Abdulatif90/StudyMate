import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 p-4 text-center sm:p-8">
      <h1 className="text-3xl font-semibold">StudyMate</h1>
      <p className="text-muted-foreground max-w-md">
        Upload your study materials and get cited, sourced answers to your questions.
      </p>
      <div className="flex flex-col gap-4 sm:flex-row">
        <Button nativeButton={false} render={<Link href="/subjects">Go to Subjects</Link>} />
        <Button
          variant="outline"
          nativeButton={false}
          render={<Link href="/sign-in">Sign in</Link>}
        />
      </div>
    </div>
  );
}
