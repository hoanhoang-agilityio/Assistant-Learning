import { CenteredPage } from "@/components/layout/CenteredPage";
import { ApiKeyForm } from "@/features/api-key/components/ApiKeyForm";
import { requireSignedInUser } from "@/services/auth";

const ApiKeyPage = async () => {
  await requireSignedInUser();

  return (
    <CenteredPage>
      <ApiKeyForm />
    </CenteredPage>
  );
};

export default ApiKeyPage;
