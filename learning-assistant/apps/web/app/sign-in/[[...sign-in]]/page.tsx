import { SignIn } from "@clerk/nextjs";

import { CenteredPage } from "@/components/layout/CenteredPage";

const SignInPage = () => {
  return (
    <CenteredPage>
      <SignIn />
    </CenteredPage>
  );
};

export default SignInPage;
