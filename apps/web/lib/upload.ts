export const MAX_PDF_BYTES = 10 * 1024 * 1024;
export function validatePdf(file: File): string | null {
  if (
    !file.name.toLowerCase().endsWith(".pdf") ||
    (file.type && file.type !== "application/pdf")
  )
    return "Choose a PDF report (.pdf).";
  if (file.size === 0) return "The selected file is empty.";
  if (file.size > MAX_PDF_BYTES) return "The report must be 10 MB or smaller.";
  return null;
}
