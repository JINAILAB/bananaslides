import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";

import { ReviewPage } from "./pages/ReviewPage";
import { UploadPage } from "./pages/UploadPage";

function LegacyJobRedirect() {
  const { jobId = "" } = useParams();
  return <Navigate to={`/?job=${jobId}`} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<UploadPage />} />
        <Route path="/jobs/:jobId" element={<LegacyJobRedirect />} />
        <Route path="/jobs/:jobId/export" element={<LegacyJobRedirect />} />
        <Route path="/jobs/:jobId/review" element={<ReviewPage />} />
      </Routes>
    </BrowserRouter>
  );
}
