import { Navigate, useParams } from "react-router-dom";

export function JobPage() {
  const { jobId = "" } = useParams();
  return <Navigate to={`/?job=${jobId}`} replace />;
}
