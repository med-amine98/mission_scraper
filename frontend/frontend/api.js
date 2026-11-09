
const API_URL = "http://127.0.0.1:8000";

async function request(endpoint, options = {}) {
  const response = await fetch(`${API_URL}${endpoint}`, options);

  const data = await response.json();

  if (!response.ok) {
    throw new Error(
      data.detail?.message ||
      data.detail ||
      `Erreur HTTP ${response.status}`
    );
  }

  return data;
}

export const api = {
  getMissions: () => request("/missions"),

  getStats: () => request("/missions/stats"),

  scrapeAll: () =>
    request("/scrape/all", { method: "POST" }),

  scrapeSource: (source) =>
    request(`/scrape/${encodeURIComponent(source)}`, {
      method: "POST"
    }),

  analyze: () =>
    request("/analyze", { method: "POST" }),

  importCSV: (file) => {
    const formData = new FormData();
    formData.append("file", file);

    return request("/import/csv", {
      method: "POST",
      body: formData
    });
  }
};
