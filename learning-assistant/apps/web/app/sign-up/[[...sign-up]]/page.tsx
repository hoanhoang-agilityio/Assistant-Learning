import { SignUp } from "@clerk/nextjs";

import { CenteredPage } from "@/components/layout/CenteredPage";

const SignUpPage = () => {
  return (
    <CenteredPage>
      <SignUp />
    </CenteredPage>
  );
};

export default SignUpPage;
