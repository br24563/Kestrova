/**
 * Loading Spinner Component.
 *
 * Displays a spinning indicator during async operations.
 */

interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg";
  message?: string;
}

export function LoadingSpinner({ size = "md", message }: LoadingSpinnerProps) {
  const sizeClasses = {
    sm: "w-4 h-4 border-2",
    md: "w-8 h-8 border-3",
    lg: "w-12 h-12 border-4",
  };

  return (
    <div className="flex flex-col items-center justify-center p-4">
      <div
        className={`${sizeClasses[size]} border-optical-200 border-t-optical-600 rounded-full animate-spin`}
      />
      {message && <p className="mt-2 text-sm text-gray-500">{message}</p>}
    </div>
  );
}
