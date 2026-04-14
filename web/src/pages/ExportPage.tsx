import { Navigate, useParams } from "react-router-dom";

export function ExportPage() {
  const { jobId = "" } = useParams();
  return <Navigate to={`/?job=${jobId}`} replace />;
}
