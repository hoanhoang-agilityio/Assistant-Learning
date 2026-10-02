import { CenteredPage } from "@/components/layout/CenteredPage";
import { MemoryPanel } from "@/features/memory/components/MemoryPanel";
import { requireSignedInUser } from "@/services/auth";

const MemoryPage = async () => {
  await requireSignedInUser();

  return (
    <CenteredPage>
      <MemoryPanel />
    </CenteredPage>
  );
};

export default MemoryPage;
