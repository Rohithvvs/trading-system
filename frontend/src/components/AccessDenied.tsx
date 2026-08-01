import React from "react";
import { useNavigate } from "react-router-dom";

export interface AccessDeniedProps {
  title?: string;
  message?: string;
  returnPath?: string;
}

export const AccessDenied: React.FC<AccessDeniedProps> = ({
  title = "Access Denied",
  message = "You do not have permission to view or access this feature.",
  returnPath = "/markets",
}) => {
  const navigate = useNavigate();

  return (
    <div
      data-testid="access-denied-view"
      className="page-container flex flex-col items-center justify-center min-h-[60vh] text-center px-4"
      style={{ padding: "32px 16px" }}
    >
      <div className="bg-red-500/10 text-red-400 p-4 rounded-full mb-4">
        <svg
          width="48"
          height="48"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
      </div>
      <h1 className="text-2xl font-bold text-gray-100 mb-2">{title}</h1>
      <p className="text-gray-400 max-w-md mb-6">{message}</p>
      <button
        type="button"
        onClick={() => navigate(returnPath)}
        className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-md transition-colors"
        data-testid="access-denied-return-btn"
      >
        Back to Markets
      </button>
    </div>
  );
};
