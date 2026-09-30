import { AppShell } from "@/components/layout/AppShell";
import { requireSignedInUser } from "@/services/auth";

const Home = async () => {
  await requireSignedInUser();

  return <AppShell />;
};

export default Home;
