import { connection } from "next/server";

import { AppShell } from "@/components/layout/AppShell";
import { getAvailableProviders } from "@/services/llm/providers";

const Home = async () => {
  //TODO: Provider keys are read per request, so adding a key needs no rebuild.
  await connection();

  return <AppShell availableProviders={getAvailableProviders()} />;
};

export default Home;
