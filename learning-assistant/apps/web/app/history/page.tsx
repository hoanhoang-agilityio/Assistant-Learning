import { CenteredPage } from "@/components/layout/CenteredPage";
import { HistoryView } from "@/features/history/components/HistoryView";
import { fetchLearningHistory } from "@/features/history/services/learning-history";
import { requireSignedInUser } from "@/services/auth";

const HistoryPage = async () => {
  const userId = await requireSignedInUser();

  return (
    <CenteredPage>
      <HistoryView history={await fetchLearningHistory(userId)} />
    </CenteredPage>
  );
};

export default HistoryPage;
