import { ApiKeyForm } from "@/features/api-key/components/ApiKeyForm";

const ApiKeyPage = () => {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 p-4 font-sans text-slate-800 dark:bg-slate-900 dark:text-slate-100">
      <ApiKeyForm />
    </main>
  );
};

export default ApiKeyPage;
