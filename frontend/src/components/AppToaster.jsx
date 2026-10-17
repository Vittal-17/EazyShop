import { useEffect } from "react";
import { Toaster, useToasterStore, toast } from "react-hot-toast";

const AppToaster = () => {
  const { toasts } = useToasterStore();

  const TOAST_LIMIT = 1;

  useEffect(() => {
    toasts.forEach((t, index) => {
      // 1. The Limit: Instantly dismiss older toasts if a new one arrives
      if (t.visible && index >= TOAST_LIMIT) {
        toast.dismiss(t.id);
      }

      // 2. The Nuclear Option: Force kill ANY visible toast after 3 seconds
      if (t.visible) {
        setTimeout(() => {
          toast.dismiss(t.id);
        }, 2000); 
      }
    });
  }, [toasts]);

  return (
    <Toaster
      position="bottom-right"
      gutter={12}
      reverseOrder={false}
      toastOptions={{
        // We still keep this here for desktop users
        duration: 3000, 
        style: {
          background: "#ffffff",
          color: "#1f2937",
          border: "1px solid #e5e7eb",
          borderRadius: "14px",
          padding: "16px",
          fontSize: "15px",
          fontWeight: "600",
          boxShadow: "0 12px 30px rgba(0,0,0,.18)",
          touchAction: "pan-y",
        },
        success: {
          iconTheme: { primary: "#16a34a", secondary: "#fff" },
        },
        error: {
          iconTheme: { primary: "#dc2626", secondary: "#fff" },
        },
      }}
    />
  );
};

export default AppToaster;