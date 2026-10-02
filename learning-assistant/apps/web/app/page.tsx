import { RETAKE_SEARCH_PARAM } from "@repo/shared/constants/routes";
import { z } from "zod";

import { AppShell } from "@/components/layout/AppShell";
import { requireSignedInUser } from "@/services/auth";

interface HomeProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

const Home = async ({ searchParams }: HomeProps) => {
  await requireSignedInUser();

  // Whether the conversation is the user's is checked when it is opened.
  const retake = z.uuid().safeParse((await searchParams)[RETAKE_SEARCH_PARAM]);

  return <AppShell retakeId={retake.success ? retake.data : null} />;
};

export default Home;
