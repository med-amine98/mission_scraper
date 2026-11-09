const API_URL = 'http://127.0.0.1:8000'

async function request(endpoint, options = {}) {
  let response

  try {
    response = await fetch(`${API_URL}${endpoint}`, {
      ...options,
      headers: {
        ...(options.body instanceof FormData
          ? {}
          : { 'Content-Type': 'application/json' }),
        ...options.headers
      }
    })
  } catch {
    throw new Error(
      `Backend inaccessible : impossible de contacter ${API_URL}. Vérifiez que FastAPI fonctionne sur le port 8000.`
    )
  }

  const text = await response.text()
  let data

  try {
    data = text ? JSON.parse(text) : {}
  } catch {
    data = { message: text }
  }

  if (!response.ok) {
    throw new Error(
      data.detail?.message ||
      data.detail ||
      data.message ||
      `Erreur HTTP ${response.status}`
    )
  }

  return data
}

export const api = {
  getMissions: () => request('/missions'),

  getMission: (id) => request(`/missions/${id}`),

  getStats: () => request('/missions/stats'),

  scrapeAll: () => request('/scrape/all', { method: 'POST' }),

  scrapeSource: (source) =>
    request(`/scrape/${encodeURIComponent(source)}`, {
      method: 'POST'
    }),

  analyze: () => request('/analyze', { method: 'POST' }),

  importCSV: (file) => {
    const formData = new FormData()
    formData.append('file', file)

    return request('/import/csv', {
      method: 'POST',
      body: formData
    })
  },

  health: () => request('/health'),

  // CV / Candidate endpoints
  getCVs: () => request('/api/cvs'),

  getCV: (id) => request(`/api/cvs/${id}`),

  createCV: (candidateData) =>
    request('/api/cvs', {
      method: 'POST',
      body: JSON.stringify(candidateData)
    }),

  uploadCVs: (files) => {
    const formData = new FormData()
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i])
    }
    return request('/api/cvs/upload', {
      method: 'POST',
      body: formData
    })
  },

  deleteCV: (id) => request(`/api/cvs/${id}`, { method: 'DELETE' }),

  deleteAllCVs: () => request('/api/cvs', { method: 'DELETE' }),

  deleteAllMissions: () => request('/missions', { method: 'DELETE' }),

  // Matching endpoints
  matchMission: (missionId) => request(`/api/match/mission/${missionId}`),

  matchCV: (cvId) => request(`/api/match/cv/${cvId}`),

  matchOverview: () => request('/api/match/overview')
}
