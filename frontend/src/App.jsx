import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import './App.css'

function extractMissions(data) {
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.missions)) return data.missions
  if (Array.isArray(data?.items)) return data.items
  if (Array.isArray(data?.data)) return data.data
  return []
}

function getPlatformClass(source) {
  const s = String(source || '').toLowerCase()
  if (s.includes('turnover') || s.includes('free-work')) return 'badge-turnover'
  if (s.includes('hitech')) return 'badge-hitech'
  if (s.includes('littlebig')) return 'badge-littlebig'
  return 'badge-other'
}

function getPlatformDisplayName(source) {
  const s = String(source || '').toLowerCase()
  if (s.includes('turnover') || s.includes('free-work')) return 'Turnover-IT'
  if (s.includes('hitech')) return 'HiTechPros'
  if (s.includes('littlebig')) return 'LittleBig Connection'
  return source || 'Autre'
}

export default function App() {
  // Navigation
  const [activePage, setActivePage] = useState('Dashboard')

  // Data states
  const [missions, setMissions] = useState([])
  const [candidates, setCandidates] = useState([])
  const [stats, setStats] = useState({ total_missions: 0, total_candidates: 0, sources: {} })
  
  // Loading & notification states
  const [loading, setLoading] = useState(true)
  const [candidatesLoading, setCandidatesLoading] = useState(false)
  const [scraping, setScraping] = useState(false)
  const [activeScrapingSource, setActiveScrapingSource] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [uploadingCV, setUploadingCV] = useState(false)
  const [backendOnline, setBackendOnline] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  // Filters
  const [search, setSearch] = useState('')
  const [platform, setPlatform] = useState('Toutes')

  // Modals & Active selections
  const [selectedMission, setSelectedMission] = useState(null)
  const [selectedCandidate, setSelectedCandidate] = useState(null)
  const [analysisResult, setAnalysisResult] = useState(null)
  const [showAddCVModal, setShowAddCVModal] = useState(false)
  const [cvTab, setCvTab] = useState('upload') // 'upload' or 'manual'

  // Manual CV Form
  const [manualCV, setManualCV] = useState({
    name: '',
    title: '',
    email: '',
    phone: '',
    experience_years: 0,
    skills: '',
    summary: '',
    raw_text: ''
  })

  // Matching states
  const [matchingMode, setMatchingMode] = useState('mission') // 'mission', 'cv', 'matrix'
  const [matchingMissionId, setMatchingMissionId] = useState('')
  const [matchingCvId, setMatchingCvId] = useState('')
  const [matchResults, setMatchResults] = useState(null)
  const [matchLoading, setMatchLoading] = useState(false)
  const [matrixResults, setMatrixResults] = useState(null)

  // -------------------------------------------------------------
  // Data Fetching
  // -------------------------------------------------------------
  async function checkBackend() {
    try {
      await api.health()
      setBackendOnline(true)
      return true
    } catch {
      setBackendOnline(false)
      return false
    }
  }

  async function loadMissions(showLoader = true) {
    try {
      if (showLoader) setLoading(true)
      setError('')
      const data = await api.getMissions()
      const list = extractMissions(data)
      setMissions(list)
      return list
    } catch (err) {
      setError(err.message)
      return []
    } finally {
      setLoading(false)
    }
  }

  async function loadCandidates(showLoader = true) {
    try {
      if (showLoader) setCandidatesLoading(true)
      const data = await api.getCVs()
      setCandidates(Array.isArray(data) ? data : [])
    } catch (err) {
      console.error('Erreur chargement CVs:', err)
    } finally {
      setCandidatesLoading(false)
    }
  }

  async function loadStats() {
    try {
      const data = await api.getStats()
      if (data) setStats(data)
    } catch (err) {
      console.warn('Erreur stats:', err)
    }
  }

  async function refreshAll() {
    await checkBackend()
    await Promise.all([loadMissions(), loadCandidates(), loadStats()])
  }

  useEffect(() => {
    refreshAll()
  }, [])

  // -------------------------------------------------------------
  // Scraping Actions
  // -------------------------------------------------------------
  async function launchScrapeAll() {
    try {
      setScraping(true)
      setError('')
      setMessage('⚡ Scraping en cours sur Turnover-IT, HiTechPros et LittleBig Connection... Veuillez patienter.')
      const res = await api.scrapeAll()
      await refreshAll()
      setMessage(`✓ Scraping terminé avec succès : ${res.total_processed ?? 0} offres traitées au total.`)
    } catch (err) {
      setError(err.message)
      setMessage('')
    } finally {
      setScraping(false)
    }
  }

  async function launchScrapeSingle(sourceKey) {
    try {
      setActiveScrapingSource(sourceKey)
      setError('')
      setMessage(`⚡ Scraping en cours sur ${sourceKey}...`)
      const res = await api.scrapeSource(sourceKey)
      await refreshAll()
      setMessage(`✓ Scraping ${sourceKey} terminé : ${res.offers_processed ?? 0} offres collectées.`)
    } catch (err) {
      setError(err.message)
      setMessage('')
    } finally {
      setActiveScrapingSource(null)
    }
  }

  // -------------------------------------------------------------
  // CV Upload & Creation
  // -------------------------------------------------------------
  async function handleCVFilesUpload(e) {
    const files = e.target.files
    if (!files || files.length === 0) return

    try {
      setUploadingCV(true)
      setError('')
      setMessage(`📄 Analyse et parsing de ${files.length} CV(s)...`)
      const res = await api.uploadCVs(files)
      await loadCandidates(false)
      await loadStats()
      setMessage(`✓ ${res.uploaded_count ?? files.length} CV(s) importé(s) et analysé(s) avec succès !`)
      setShowAddCVModal(false)
    } catch (err) {
      setError(err.message)
      setMessage('')
    } finally {
      setUploadingCV(false)
      e.target.value = ''
    }
  }

  async function handleManualCVSubmit(e) {
    e.preventDefault()
    if (!manualCV.name.trim()) {
      setError('Veuillez renseigner le nom du candidat.')
      return
    }

    try {
      setUploadingCV(true)
      setError('')
      await api.createCV(manualCV)
      await loadCandidates(false)
      await loadStats()
      setMessage(`✓ Candidat ${manualCV.name} ajouté avec succès.`)
      setShowAddCVModal(false)
      setManualCV({
        name: '',
        title: '',
        email: '',
        phone: '',
        experience_years: 0,
        skills: '',
        summary: '',
        raw_text: ''
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setUploadingCV(false)
    }
  }

  async function handleDeleteCV(id, name) {
    if (!window.confirm(`Voulez-vous vraiment supprimer le CV de ${name} ?`)) return
    try {
      await api.deleteCV(id)
      await loadCandidates(false)
      await loadStats()
      setMessage(`✓ Candidat supprimé.`)
      if (selectedCandidate?.id === id) setSelectedCandidate(null)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteAllCVs() {
    if (!window.confirm('Voulez-vous vraiment supprimer TOUS les CVs de votre vivier ? Cette action est irréversible.')) return
    try {
      await api.deleteAllCVs()
      await loadCandidates(false)
      await loadStats()
      setMessage('✓ Tous les CVs ont été supprimés.')
      setSelectedCandidate(null)
      setMatchResults(null)
      setMatrixResults(null)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteAllMissions() {
    if (!window.confirm('Voulez-vous vraiment supprimer toutes les offres pour relancer un scraping à zéro ?')) return
    try {
      await api.deleteAllMissions()
      await loadMissions(false)
      await loadStats()
      setMessage('✓ Toutes les offres ont été supprimées. Vous pouvez relancer un scraping vierge.')
      setSelectedMission(null)
      setMatchResults(null)
      setMatrixResults(null)
    } catch (err) {
      setError(err.message)
    }
  }

  // -------------------------------------------------------------
  // Smart Matching Logic
  // -------------------------------------------------------------
  async function runMatchForMission(missionId) {
    if (!missionId) return
    try {
      setMatchLoading(true)
      setMatchingMissionId(String(missionId))
      setMatchingMode('mission')
      setActivePage('Matching Idéal')
      setError('')
      const res = await api.matchMission(missionId)
      setMatchResults(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setMatchLoading(false)
    }
  }

  async function runMatchForCV(cvId) {
    if (!cvId) return
    try {
      setMatchLoading(true)
      setMatchingCvId(String(cvId))
      setMatchingMode('cv')
      setActivePage('Matching Idéal')
      setError('')
      const res = await api.matchCV(cvId)
      setMatchResults(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setMatchLoading(false)
    }
  }

  async function runMatrixOverview() {
    try {
      setMatchLoading(true)
      setMatchingMode('matrix')
      setError('')
      const res = await api.matchOverview()
      setMatrixResults(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setMatchLoading(false)
    }
  }

  // -------------------------------------------------------------
  // Filtered Missions
  // -------------------------------------------------------------
  const filteredMissions = useMemo(() => {
    return missions.filter((m) => {
      const text = [
        m.title,
        m.company,
        m.location,
        m.skills,
        m.description,
        m.rate
      ].join(' ').toLowerCase()

      const s = (m.source || '').toLowerCase()
      const matchesSearch = !search || text.includes(search.toLowerCase())

      let matchesPlatform = true
      if (platform === 'Turnover-IT') matchesPlatform = s.includes('turnover') || s.includes('free-work')
      else if (platform === 'HiTechPros') matchesPlatform = s.includes('hitech')
      else if (platform === 'LittleBig Connection') matchesPlatform = s.includes('littlebig')

      return matchesSearch && matchesPlatform
    })
  }, [missions, search, platform])

  // Stats cards data
  const statCards = [
    {
      label: 'Total des missions',
      value: missions.length,
      icon: '📋',
      color: '#4169e1',
      subtext: 'Dans les 3 sources'
    },
    {
      label: 'Turnover-IT',
      value: missions.filter(m => `${m.source || ''}`.toLowerCase().includes('turnover') || `${m.source || ''}`.toLowerCase().includes('free-work')).length,
      icon: '💼',
      color: '#3b82f6',
      subtext: 'Free-Work Freelance'
    },
    {
      label: 'HiTechPros',
      value: missions.filter(m => `${m.source || ''}`.toLowerCase().includes('hitech')).length,
      icon: '🚀',
      color: '#10b981',
      subtext: 'Missions en direct'
    },
    {
      label: 'LittleBig Connection',
      value: missions.filter(m => `${m.source || ''}`.toLowerCase().includes('littlebig')).length,
      icon: '🌐',
      color: '#f59e0b',
      subtext: 'Appels d’offres RFP'
    },
    {
      label: 'CVs & Candidats',
      value: candidates.length,
      icon: '👥',
      color: '#8b5cf6',
      subtext: 'Profils enregistrés'
    }
  ]

  return (
    <div className="app">
      {/* --------------------------------------------------------- */}
      {/* SIDEBAR */}
      {/* --------------------------------------------------------- */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">IL</div>
          <div>
            <h2>I-LEAD</h2>
            <span>MISSION & MATCHING AI</span>
          </div>
        </div>

        <div className="menu-label">MENU PRINCIPAL</div>

        {[
          ['Dashboard', '▦'],
          ['Missions', '▤'],
          ['Gestion des CVs', '👥'],
          ['Matching Idéal', '🎯'],
          ['Plateformes', '🌐'],
          ['Analyse IA', '✧']
        ].map(([name, icon]) => (
          <button
            key={name}
            className={`nav-item ${activePage === name ? 'active' : ''}`}
            onClick={() => {
              setActivePage(name)
              if (name === 'Matching Idéal' && !matchResults && missions.length > 0) {
                runMatchForMission(missions[0].id)
              }
            }}
          >
            <span>{icon}</span>
            {name}
            {name === 'Gestion des CVs' && candidates.length > 0 && (
              <span className="nav-badge">{candidates.length}</span>
            )}
            {name === 'Missions' && missions.length > 0 && (
              <span className="nav-badge">{missions.length}</span>
            )}
          </button>
        ))}

        <div className="sidebar-bottom">
          <div className={`status-indicator ${backendOnline ? 'online' : 'offline'}`}></div>
          <div>
            <strong>Backend FastAPI</strong>
            <span>{backendOnline ? 'Port 8000 Connecté' : 'Hors ligne'}</span>
          </div>
        </div>
      </aside>

      {/* --------------------------------------------------------- */}
      {/* MAIN CONTENT AREA */}
      {/* --------------------------------------------------------- */}
      <main className="main-content">
        {/* TOPBAR */}
        <header className="topbar">
          <div>
            <span className="breadcrumb">I-LEAD / {activePage.toUpperCase()}</span>
            <h1>{activePage}</h1>
          </div>

          <div className="top-actions">
            <button
              className="refresh-btn"
              onClick={refreshAll}
              disabled={loading || scraping}
              title="Rafraîchir les données"
            >
              ↻ Actualiser
            </button>
            <button
              className="btn-primary"
              onClick={() => setShowAddCVModal(true)}
            >
              + Ajouter des CVs
            </button>
            <div className="avatar">IL</div>
          </div>
        </header>

        {/* NOTIFICATIONS */}
        {error && (
          <div className="error-message">
            <div>
              <strong>⚠️ Erreur : </strong> {error}
            </div>
            <button onClick={() => setError('')}>✕</button>
          </div>
        )}

        {message && (
          <div className="success-message">
            <div>{message}</div>
            <button onClick={() => setMessage('')}>✕</button>
          </div>
        )}

        {/* ========================================================= */}
        {/* VIEW 1: DASHBOARD */}
        {/* ========================================================= */}
        {activePage === 'Dashboard' && (
          <>
            <section className="welcome">
              <div>
                <span className="welcome-tag">INTELLIGENCE COMMERCIALE & RECRUTEMENT</span>
                <h2>Scraper IT & Matching de CVs I-Lead</h2>
                <p>
                  Collectez les missions freelance en temps réel depuis <strong>Turnover-IT</strong>,{' '}
                  <strong>HiTechPros</strong> et <strong>LittleBig Connection</strong>, et faites matcher
                  automatiquement votre vivier de CVs pour trouver le candidat idéal pour chaque mission !
                </p>
              </div>

              <div className="welcome-actions">
                <button
                  className="scrape-btn"
                  onClick={launchScrapeAll}
                  disabled={scraping}
                >
                  {scraping ? '⏳ Scraping en cours...' : '⚡ Lancer le scraping global'}
                </button>
              </div>
            </section>

            {/* STATS GRID */}
            <section className="stats-grid">
              {statCards.map((stat) => (
                <div className="stat-card" key={stat.label}>
                  <div className="stat-top">
                    <span>{stat.label}</span>
                    <span className="stat-icon" style={{ color: stat.color }}>{stat.icon}</span>
                  </div>
                  <strong>{loading ? '...' : stat.value}</strong>
                  <small>{stat.subtext}</small>
                </div>
              ))}
            </section>

            {/* THREE SOURCES SUMMARY CARDS */}
            <section className="platform-section">
              <div className="section-heading">
                <div>
                  <h2>Sources connectées & Scraping direct</h2>
                  <p>Déclenchez le scraping ciblé par source ou consultez les volumes collectés.</p>
                </div>
              </div>

              <div className="platform-grid">
                {[
                  {
                    key: 'turnover_it',
                    name: 'Turnover-IT (Free-Work)',
                    count: missions.filter(m => `${m.source || ''}`.toLowerCase().includes('turnover') || `${m.source || ''}`.toLowerCase().includes('free-work')).length,
                    desc: 'Missions IT freelance, régie & forfait',
                    icon: '💼',
                    color: '#eaf0ff'
                  },
                  {
                    key: 'hitechpros',
                    name: 'HiTechPros',
                    count: missions.filter(m => `${m.source || ''}`.toLowerCase().includes('hitech')).length,
                    desc: 'Portail n°1 des ESN & indépendants IT',
                    icon: '🚀',
                    color: '#e8f8f1'
                  },
                  {
                    key: 'littlebig_connection',
                    name: 'LittleBig Connection',
                    count: missions.filter(m => `${m.source || ''}`.toLowerCase().includes('littlebig')).length,
                    desc: 'Appels d’offres RFP grands comptes',
                    icon: '🌐',
                    color: '#fff2e8'
                  }
                ].map((p) => (
                  <div className="platform-card" key={p.key}>
                    <div className="platform-icon" style={{ background: p.color }}>
                      {p.icon}
                    </div>
                    <div className="platform-info">
                      <h3>{p.name}</h3>
                      <p>{p.desc}</p>
                      <span className="platform-count"><strong>{p.count}</strong> offres en base</span>
                    </div>
                    <button
                      className="btn-source-scrape"
                      onClick={() => launchScrapeSingle(p.key)}
                      disabled={activeScrapingSource === p.key || scraping}
                    >
                      {activeScrapingSource === p.key ? 'Scraping...' : 'Scanner ↻'}
                    </button>
                  </div>
                ))}
              </div>
            </section>

            {/* QUICK PREVIEW: TOP RECENT MISSIONS WITH MATCH BUTTON */}
            <section className="missions-section">
              <div className="section-heading">
                <div>
                  <h2>Dernières opportunités collectées</h2>
                  <p>Cliquez sur "Trouver le CV idéal" pour faire matcher vos candidats instantanément.</p>
                </div>
                <button className="view-all-btn" onClick={() => setActivePage('Missions')}>
                  Voir toutes les missions ({missions.length}) →
                </button>
              </div>

              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>MISSION & COMPÉTENCES</th>
                      <th>LOCALISATION</th>
                      <th>SOURCE</th>
                      <th>ACTION MATCHING</th>
                      <th>LIEN</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <tr><td colSpan="5" className="empty">Chargement des missions...</td></tr>
                    ) : missions.slice(0, 6).map((m) => (
                      <tr key={m.id || m.url}>
                        <td>
                          <strong>{m.title || 'Sans titre'}</strong>
                          <div className="skills-tags">
                            {(m.skills || '').split(',').slice(0, 4).map((s, idx) => (
                              s.trim() && <span key={idx} className="skill-tag">{s.trim()}</span>
                            ))}
                          </div>
                        </td>
                        <td>{m.location || 'France / Télétravail'}</td>
                        <td>
                          <span className={`source-badge ${getPlatformClass(m.source)}`}>
                            {getPlatformDisplayName(m.source)}
                          </span>
                        </td>
                        <td>
                          <button
                            className="btn-match-action"
                            onClick={() => runMatchForMission(m.id)}
                          >
                            🎯 Trouver le CV idéal
                          </button>
                        </td>
                        <td>
                          {m.url && (
                            <a href={m.url} target="_blank" rel="noreferrer" className="view-link">
                              Ouvrir ↗
                            </a>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}

        {/* ========================================================= */}
        {/* VIEW 2: MISSIONS (TABLE COMPLETE) */}
        {/* ========================================================= */}
        {activePage === 'Missions' && (
          <section className="missions-section">
            <div className="section-heading">
              <div>
                <h2>Toutes les missions collectées ({filteredMissions.length})</h2>
                <p>Recherchez et filtrez par source, compétence ou mots-clés.</p>
              </div>

              <div className="heading-actions">
                {missions.length > 0 && (
                  <button
                    className="btn-danger-outline"
                    onClick={handleDeleteAllMissions}
                    title="Supprimer toutes les offres pour relancer un scraping vierge"
                  >
                    🗑 Vider les offres
                  </button>
                )}
                <button
                  className="scrape-btn-sm"
                  onClick={launchScrapeAll}
                  disabled={scraping}
                >
                  {scraping ? 'Scraping...' : '⚡ Re-Scraper les 3 sources'}
                </button>
              </div>
            </div>

            {/* FILTERS */}
            <div className="filters">
              <input
                type="text"
                placeholder="⌕ Rechercher un intitulé (ex: Python, DevOps, Chef de projet, Paris, React...)"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />

              <select value={platform} onChange={(e) => setPlatform(e.target.value)}>
                <option value="Toutes">Toutes les plateformes ({missions.length})</option>
                <option value="Turnover-IT">Turnover-IT / Free-Work</option>
                <option value="HiTechPros">HiTechPros</option>
                <option value="LittleBig Connection">LittleBig Connection</option>
              </select>
            </div>

            {/* TABLE */}
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>MISSION & COMPÉTENCES REQUISES</th>
                    <th>ENTREPRISE & LIEU</th>
                    <th>TJM / TARIF</th>
                    <th>SOURCE</th>
                    <th>MATCHING CV</th>
                    <th>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan="6" className="empty">Chargement des missions...</td></tr>
                  ) : filteredMissions.length === 0 ? (
                    <tr><td colSpan="6" className="empty">Aucune mission trouvée pour ces critères.</td></tr>
                  ) : (
                    filteredMissions.map((mission) => (
                      <tr key={mission.id || mission.url}>
                        <td>
                          <strong>{mission.title || 'Mission sans titre'}</strong>
                          <div className="skills-tags">
                            {(mission.skills || '').split(',').slice(0, 5).map((s, idx) => (
                              s.trim() && <span key={idx} className="skill-tag">{s.trim()}</span>
                            ))}
                          </div>
                        </td>
                        <td>
                          <div>{mission.company || 'Client confidentiel'}</div>
                          <small>{mission.location || 'Non précisé'}</small>
                        </td>
                        <td>
                          <span className="rate-badge">{mission.rate || 'Sur devis / TJM'}</span>
                        </td>
                        <td>
                          <span className={`source-badge ${getPlatformClass(mission.source)}`}>
                            {getPlatformDisplayName(mission.source)}
                          </span>
                        </td>
                        <td>
                          <button
                            className="btn-match-action"
                            onClick={() => runMatchForMission(mission.id)}
                            title="Calculer le matching avec votre vivier de CVs"
                          >
                            🎯 Trouver le CV idéal
                          </button>
                        </td>
                        <td>
                          <div className="row-actions">
                            <button
                              className="btn-icon"
                              onClick={() => setSelectedMission(mission)}
                              title="Voir la fiche détaillée"
                            >
                              👁
                            </button>
                            {mission.url && (
                              <a
                                href={mission.url}
                                target="_blank"
                                rel="noreferrer"
                                className="view-link"
                                title="Voir l'offre originale"
                              >
                                Offre ↗
                              </a>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* ========================================================= */}
        {/* VIEW 3: GESTION DES CVS & CANDIDATS (NEW) */}
        {/* ========================================================= */}
        {activePage === 'Gestion des CVs' && (
          <section className="candidates-section">
            <div className="section-heading">
              <div>
                <h2>Vivier de Candidats & CVs ({candidates.length})</h2>
                <p>Ajoutez vos CVs (PDF, DOCX, TXT) pour les croiser avec les offres détectées.</p>
              </div>

              <div className="heading-actions">
                {candidates.length > 0 && (
                  <button
                    className="btn-danger-outline"
                    onClick={handleDeleteAllCVs}
                    title="Vider tous les CVs"
                  >
                    🗑 Vider tous les CVs
                  </button>
                )}
                <button className="btn-primary" onClick={() => setShowAddCVModal(true)}>
                  + Importer ou ajouter un CV
                </button>
              </div>
            </div>

            {/* DRAG AND DROP / UPLOAD ZONE BANNER */}
            <div className="cv-upload-dropzone">
              <div className="dropzone-content">
                <span className="dropzone-icon">📁</span>
                <div>
                  <h3>Déposer vos CVs ici (PDF, DOCX, TXT)</h3>
                  <p>L'IA extrait automatiquement le nom, les coordonnées, les compétences et les années d'expérience.</p>
                </div>
              </div>
              <label className="btn-upload-file">
                {uploadingCV ? '⏳ Analyse en cours...' : 'Parcourir les fichiers...'}
                <input
                  type="file"
                  multiple
                  accept=".pdf,.docx,.doc,.txt,.md"
                  onChange={handleCVFilesUpload}
                  disabled={uploadingCV}
                  hidden
                />
              </label>
            </div>

            {/* CANDIDATES LIST */}
            {candidatesLoading ? (
              <div className="empty">Chargement des candidats...</div>
            ) : candidates.length === 0 ? (
              <div className="empty-state-card">
                <span className="empty-icon">👥</span>
                <h3>Aucun CV enregistré pour le moment</h3>
                <p>Ajoutez votre premier candidat par fichier PDF/Word ou en saisie directe pour trouver les offres idéales.</p>
                <button className="btn-primary" onClick={() => setShowAddCVModal(true)}>
                  Ajouter un premier CV maintenant
                </button>
              </div>
            ) : (
              <div className="candidates-grid">
                {candidates.map((c) => (
                  <div className="candidate-card" key={c.id}>
                    <div className="candidate-card-header">
                      <div className="candidate-avatar">
                        {(c.name || 'C').substring(0, 2).toUpperCase()}
                      </div>
                      <div className="candidate-meta">
                        <h3>{c.name}</h3>
                        <span className="candidate-title">{c.title || 'Consultant IT'}</span>
                      </div>
                      <button
                        className="btn-delete"
                        onClick={() => handleDeleteCV(c.id, c.name)}
                        title="Supprimer ce CV"
                      >
                        🗑
                      </button>
                    </div>

                    <div className="candidate-contact">
                      {c.email && <span>✉ {c.email}</span>}
                      {c.phone && <span>📞 {c.phone}</span>}
                      <span className="exp-badge">
                        ⏱ {c.experience_years ? `${c.experience_years} ans d'expérience` : "Expérience confirmée"}
                      </span>
                    </div>

                    <div className="candidate-skills">
                      <strong>Compétences clés :</strong>
                      <div className="skills-tags">
                        {(c.skills || '').split(',').slice(0, 6).map((s, idx) => (
                          s.trim() && <span key={idx} className="skill-tag">{s.trim()}</span>
                        ))}
                      </div>
                    </div>

                    {c.summary && (
                      <p className="candidate-summary">"{c.summary.substring(0, 140)}..."</p>
                    )}

                    <div className="candidate-card-footer">
                      <button
                        className="btn-match-action full"
                        onClick={() => runMatchForCV(c.id)}
                      >
                        🎯 Trouver les offres idéales
                      </button>
                      <button
                        className="btn-secondary"
                        onClick={() => setSelectedCandidate(c)}
                      >
                        Voir la fiche
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* ========================================================= */}
        {/* VIEW 4: MATCHING INTELLIGENT (NEW) */}
        {/* ========================================================= */}
        {activePage === 'Matching Idéal' && (
          <section className="matching-section">
            <div className="section-heading">
              <div>
                <h2>Moteur de Matching Intelligent (CV ↔ Offres)</h2>
                <p>Identifiez en un clic le meilleur candidat pour une offre ou les meilleures offres pour un profil.</p>
              </div>

              {/* TABS */}
              <div className="matching-tabs">
                <button
                  className={`tab-btn ${matchingMode === 'mission' ? 'active' : ''}`}
                  onClick={() => setMatchingMode('mission')}
                >
                  🎯 Trouver le CV idéal pour une offre
                </button>
                <button
                  className={`tab-btn ${matchingMode === 'cv' ? 'active' : ''}`}
                  onClick={() => {
                    setMatchingMode('cv')
                    if (candidates.length > 0 && !matchingCvId) {
                      runMatchForCV(candidates[0].id)
                    }
                  }}
                >
                  💼 Trouver les offres idéales pour un CV
                </button>
                <button
                  className={`tab-btn ${matchingMode === 'matrix' ? 'active' : ''}`}
                  onClick={runMatrixOverview}
                >
                  📊 Matrice de matching globale
                </button>
              </div>
            </div>

            {/* SUB-VIEW A: MATCH CANDIDATES FOR SELECTED MISSION */}
            {matchingMode === 'mission' && (
              <div>
                {/* SELECTOR BAR */}
                <div className="matching-selector-box">
                  <label>Choisir la mission à pourvoir :</label>
                  <select
                    value={matchingMissionId}
                    onChange={(e) => runMatchForMission(e.target.value)}
                  >
                    <option value="">-- Sélectionner une offre parmi les {missions.length} collectées --</option>
                    {missions.map((m) => (
                      <option key={m.id} value={String(m.id)}>
                        [{getPlatformDisplayName(m.source)}] {m.title} - {m.location || 'France'}
                      </option>
                    ))}
                  </select>
                </div>

                {matchLoading ? (
                  <div className="empty">Calcul du score d'adéquation en cours...</div>
                ) : !matchResults?.mission ? (
                  <div className="empty-state-card">
                    <span className="empty-icon">🎯</span>
                    <h3>Sélectionnez une mission pour trouver le candidat idéal</h3>
                    <p>Choisissez une mission dans la liste déroulante ci-dessus ou depuis le tableau des missions.</p>
                  </div>
                ) : (
                  <div className="match-detail-container">
                    {/* MISSION SUMMARY CARD */}
                    <div className="match-mission-banner">
                      <div className="mission-banner-info">
                        <span className={`source-badge ${getPlatformClass(matchResults.mission.source)}`}>
                          {getPlatformDisplayName(matchResults.mission.source)}
                        </span>
                        <h3>{matchResults.mission.title}</h3>
                        <p>{matchResults.mission.company || 'Client'} · 📍 {matchResults.mission.location || 'Lieu non spécifié'}</p>
                        <div className="skills-tags">
                          {(matchResults.mission.skills || '').split(',').map((s, idx) => (
                            s.trim() && <span key={idx} className="skill-tag highlight">{s.trim()}</span>
                          ))}
                        </div>
                      </div>

                      {matchResults.mission.url && (
                        <a
                          href={matchResults.mission.url}
                          target="_blank"
                          rel="noreferrer"
                          className="btn-primary"
                        >
                          Consulter l'offre ↗
                        </a>
                      )}
                    </div>

                    {/* CANDIDATES RANKED BY MATCH */}
                    <div className="match-ranking-header">
                      <h3>Candidats classés par ordre de pertinence ({matchResults.matches?.length || 0}) :</h3>
                    </div>

                    {matchResults.matches?.length === 0 ? (
                      <div className="empty-state-card">
                        <p>Aucun CV n'a encore été ajouté. Ajoutez des CVs pour calculer l'adéquation.</p>
                        <button className="btn-primary" onClick={() => setShowAddCVModal(true)}>
                          + Ajouter des CVs
                        </button>
                      </div>
                    ) : (
                      <div className="match-cards-list">
                        {matchResults.matches.map((item, idx) => {
                          const { candidate, match } = item
                          const isTop = idx === 0 && match.score >= 60

                          return (
                            <div className={`match-card ${isTop ? 'top-match' : ''}`} key={candidate.id}>
                              {isTop && <div className="top-match-badge">🌟 CANDIDAT IDÉAL</div>}

                              <div className="match-card-top">
                                <div className="candidate-info">
                                  <div className="candidate-avatar">
                                    {(candidate.name || 'C').substring(0, 2).toUpperCase()}
                                  </div>
                                  <div>
                                    <h4>{candidate.name}</h4>
                                    <span>{candidate.title || 'Consultant IT'}</span>
                                  </div>
                                </div>

                                <div className="match-score-badge">
                                  <div className={`score-circle ${match.badge_class}`}>
                                    {match.score}%
                                  </div>
                                  <span className="score-verdict">{match.verdict}</span>
                                </div>
                              </div>

                              <div className="match-analysis-body">
                                <div className="match-row">
                                  <strong>💡 Avis :</strong>
                                  <span>{match.recommendation}</span>
                                </div>
                                <div className="match-row">
                                  <strong>⏱ Expérience :</strong>
                                  <span>{match.experience_fit}</span>
                                </div>

                                {/* SKILLS COMPARISON */}
                                <div className="skills-comparison">
                                  <div>
                                    <strong className="text-green">✓ Compétences validées ({(match.matched_skills || []).length}) :</strong>
                                    <div className="skills-tags">
                                      {(match.matched_skills || []).length === 0 ? (
                                        <small>Aucune correspondance directe détectée</small>
                                      ) : (
                                        (match.matched_skills || []).map((s, i) => (
                                          <span key={i} className="skill-tag skill-matched">✓ {s}</span>
                                        ))
                                      )}
                                    </div>
                                  </div>

                                  {(match.missing_skills || []).length > 0 && (
                                    <div>
                                      <strong className="text-orange">✗ Compétences requises manquantes ({(match.missing_skills || []).length}) :</strong>
                                      <div className="skills-tags">
                                        {(match.missing_skills || []).map((s, i) => (
                                          <span key={i} className="skill-tag skill-missing">✗ {s}</span>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              </div>

                              <div className="match-card-footer">
                                <button
                                  className="btn-secondary"
                                  onClick={() => setSelectedCandidate(candidate)}
                                >
                                  Voir CV complet
                                </button>
                                {candidate.email && (
                                  <a href={`mailto:${candidate.email}`} className="btn-contact">
                                    ✉ Contacter ({candidate.email})
                                  </a>
                                )}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* SUB-VIEW B: MATCH MISSIONS FOR SELECTED CANDIDATE */}
            {matchingMode === 'cv' && (
              <div>
                <div className="matching-selector-box">
                  <label>Choisir le candidat :</label>
                  <select
                    value={matchingCvId}
                    onChange={(e) => runMatchForCV(e.target.value)}
                  >
                    <option value="">-- Sélectionner un candidat parmi les {candidates.length} profils --</option>
                    {candidates.map((c) => (
                      <option key={c.id} value={String(c.id)}>
                        {c.name} ({c.title || 'Consultant'}) - {c.experience_years ? `${c.experience_years} ans` : ''}
                      </option>
                    ))}
                  </select>
                </div>

                {matchLoading ? (
                  <div className="empty">Recherche des meilleures offres en cours...</div>
                ) : !matchResults?.candidate ? (
                  <div className="empty-state-card">
                    <span className="empty-icon">💼</span>
                    <h3>Sélectionnez un candidat pour trouver les offres idéales</h3>
                    <p>Le moteur va comparer ses compétences avec l'ensemble des offres des 3 plateformes.</p>
                  </div>
                ) : (
                  <div>
                    <div className="candidate-match-banner">
                      <div className="candidate-avatar lg">
                        {(matchResults.candidate.name || 'C').substring(0, 2).toUpperCase()}
                      </div>
                      <div>
                        <h3>{matchResults.candidate.name}</h3>
                        <p>{matchResults.candidate.title} · ⏱ {matchResults.candidate.experience_years} ans d'expérience</p>
                        <div className="skills-tags">
                          {(matchResults.candidate.skills || '').split(',').map((s, i) => (
                            s.trim() && <span key={i} className="skill-tag highlight">{s.trim()}</span>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className="match-ranking-header">
                      <h3>Top missions recommandées pour ce profil ({matchResults.matches?.length || 0}) :</h3>
                    </div>

                    <div className="match-cards-list">
                      {matchResults.matches?.map((item) => {
                        const { mission, match } = item
                        return (
                          <div className="match-card" key={mission.id}>
                            <div className="match-card-top">
                              <div>
                                <span className={`source-badge ${getPlatformClass(mission.source)}`}>
                                  {getPlatformDisplayName(mission.source)}
                                </span>
                                <h4 style={{ margin: '8px 0 4px' }}>{mission.title}</h4>
                                <small>{mission.company || 'Client'} · 📍 {mission.location || 'Lieu non spécifié'}</small>
                              </div>

                              <div className="match-score-badge">
                                <div className={`score-circle ${match.badge_class}`}>
                                  {match.score}%
                                </div>
                                <span className="score-verdict">{match.verdict}</span>
                              </div>
                            </div>

                            <div className="match-analysis-body">
                              <p><strong>💡 Synthèse : </strong>{match.recommendation}</p>
                              <div className="skills-comparison">
                                <div>
                                  <strong className="text-green">✓ Compétences partagées ({(match.matched_skills || []).length}) :</strong>
                                  <div className="skills-tags">
                                    {(match.matched_skills || []).length === 0 ? (
                                      <small>Aucune compétence spécifique identifiée</small>
                                    ) : (
                                      (match.matched_skills || []).map((s, idx) => (
                                        <span key={idx} className="skill-tag skill-matched">✓ {s}</span>
                                      ))
                                    )}
                                  </div>
                                </div>
                              </div>
                            </div>

                            <div className="match-card-footer">
                              <button
                                className="btn-secondary"
                                onClick={() => setSelectedMission(mission)}
                              >
                                Fiche détaillée
                              </button>
                              {mission.url && (
                                <a
                                  href={mission.url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="btn-primary"
                                >
                                  Postuler / Voir l'offre ↗
                                </a>
                              )}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* SUB-VIEW C: GLOBAL MATRIX OVERVIEW */}
            {matchingMode === 'matrix' && (
              <div>
                <div className="section-heading">
                  <div>
                    <h3>Matrice de compatibilité globale (&gt; 65%)</h3>
                    <p>Découvrez les meilleures associations candidat-mission instantanément.</p>
                  </div>
                  <button className="refresh-btn" onClick={runMatrixOverview}>
                    ↻ Recalculer la matrice
                  </button>
                </div>

                {matchLoading ? (
                  <div className="empty">Calcul de la matrice globale...</div>
                ) : !matrixResults?.top_pairings?.length ? (
                  <div className="empty-state-card">
                    <p>Aucun match significatif (&gt; 65%) trouvé. Ajoutez d'autres CVs ou lancez un scraping pour trouver des opportunités.</p>
                  </div>
                ) : (
                  <div className="table-wrapper">
                    <table>
                      <thead>
                        <tr>
                          <th>SCORE</th>
                          <th>CANDIDAT</th>
                          <th>MISSION MATCHÉE</th>
                          <th>SOURCE</th>
                          <th>COMPÉTENCES PARTAGÉES</th>
                          <th>ACTION</th>
                        </tr>
                      </thead>
                      <tbody>
                        {matrixResults.top_pairings.map((p, idx) => (
                          <tr key={idx}>
                            <td>
                              <span className="score-badge-matrix">{p.score}%</span>
                            </td>
                            <td>
                              <strong>{p.candidate_name}</strong>
                              <small>{p.candidate_title}</small>
                            </td>
                            <td>
                              <strong>{p.mission_title}</strong>
                            </td>
                            <td>
                              <span className={`source-badge ${getPlatformClass(p.source)}`}>
                                {getPlatformDisplayName(p.source)}
                              </span>
                            </td>
                            <td>
                              <div className="skills-tags">
                                {(p.matched_skills || []).slice(0, 4).map((s, i) => (
                                  <span key={i} className="skill-tag skill-matched">{s}</span>
                                ))}
                              </div>
                            </td>
                            <td>
                              {p.url && (
                                <a href={p.url} target="_blank" rel="noreferrer" className="view-link">
                                  Voir l'offre ↗
                                </a>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {/* ========================================================= */}
        {/* VIEW 5: PLATEFORMES */}
        {/* ========================================================= */}
        {activePage === 'Plateformes' && (
          <section className="platform-section">
            <div className="section-heading">
              <div>
                <h2>Configuration & Statut des 3 Sources</h2>
                <p>Gestion et lancement individuel des scrapers.</p>
              </div>
              <button
                className="scrape-btn-sm"
                onClick={launchScrapeAll}
                disabled={scraping}
              >
                {scraping ? 'Scraping en cours...' : '⚡ Lancer le scraping global'}
              </button>
            </div>

            <div className="platforms-detailed-grid">
              {[
                {
                  id: 'turnover_it',
                  name: 'Turnover-IT / Free-Work',
                  desc: 'Portail de référence des freelances et indépendants IT.',
                  url: 'https://www.free-work.com/fr/tech-it/jobs?contracts=contractor',
                  badge: 'Turnover-IT',
                  count: missions.filter(m => `${m.source || ''}`.toLowerCase().includes('turnover') || `${m.source || ''}`.toLowerCase().includes('free-work')).length,
                  features: ['Missions freelance IT', 'Extraction automatique des compétences', 'Mise à jour en temps réel']
                },
                {
                  id: 'hitechpros',
                  name: 'HiTechPros',
                  desc: 'La 1ère bourse d’opportunités IT en France pour ESN et freelances.',
                  url: 'https://freelance.hitechpros.com/missions',
                  badge: 'HiTechPros',
                  count: missions.filter(m => `${m.source || ''}`.toLowerCase().includes('hitech')).length,
                  features: ['Missions directes ESN & clients finaux', 'Localisation et TJM indicatif', 'Pagination dynamique']
                },
                {
                  id: 'littlebig_connection',
                  name: 'LittleBig Connection',
                  desc: 'Plateforme de mise en relation grands comptes & prestataires experts.',
                  url: 'https://app.littlebigconnection.com/fr/rfp/',
                  badge: 'LittleBig Connection',
                  count: missions.filter(m => `${m.source || ''}`.toLowerCase().includes('littlebig')).length,
                  features: ['Appels d’offres RFP qualifiés', 'Missions grands comptes & CAC40', 'Profils experts et tech lead']
                }
              ].map((p) => (
                <div className="platform-detail-card" key={p.id}>
                  <div className="detail-card-header">
                    <div>
                      <span className={`source-badge ${getPlatformClass(p.id)}`}>{p.badge}</span>
                      <h3>{p.name}</h3>
                      <p>{p.desc}</p>
                    </div>
                  </div>

                  <div className="detail-stat">
                    <span>Missions en base :</span>
                    <strong>{p.count}</strong>
                  </div>

                  <ul className="feature-list">
                    {p.features.map((f, i) => (
                      <li key={i}>✓ {f}</li>
                    ))}
                  </ul>

                  <div className="detail-card-actions">
                    <button
                      className="btn-primary"
                      onClick={() => launchScrapeSingle(p.id)}
                      disabled={activeScrapingSource === p.id || scraping}
                    >
                      {activeScrapingSource === p.id ? 'Scraping...' : `Scanner ${p.name}`}
                    </button>
                    <a href={p.url} target="_blank" rel="noreferrer" className="btn-secondary">
                      Accéder au site ↗
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ========================================================= */}
        {/* VIEW 6: ANALYSE IA */}
        {/* ========================================================= */}
        {activePage === 'Analyse IA' && (
          <section className="missions-section">
            <div className="section-heading">
              <div>
                <h2>Analyse sémantique & IA des missions</h2>
                <p>Enrichissement par LLM (Claude Sonnet / GPT) des offres collectées.</p>
              </div>

              <button
                className="scrape-btn-sm"
                onClick={async () => {
                  try {
                    setAnalyzing(true)
                    setError('')
                    setMessage('Analyse IA en cours...')
                    const res = await api.analyze()
                    setAnalysisResult(res)
                    setMessage('Analyse IA terminée.')
                  } catch (err) {
                    setError(err.message)
                  } finally {
                    setAnalyzing(false)
                  }
                }}
                disabled={analyzing}
              >
                {analyzing ? 'Analyse en cours...' : '✧ Lancer l’analyse IA'}
              </button>
            </div>

            {analysisResult ? (
              <pre className="analysis-box">
                {JSON.stringify(analysisResult, null, 2)}
              </pre>
            ) : (
              <div className="empty-state-card">
                <span className="empty-icon">✧</span>
                <h3>Prêt pour l'analyse IA</h3>
                <p>Cliquez sur "Lancer l’analyse IA" pour évaluer la pertinence et les technologies dominantes des offres.</p>
              </div>
            )}
          </section>
        )}

        {/* FOOTER */}
        <footer>
          I-LEAD MISSION INTELLIGENCE & RECRUITMENT MATCHING · Version 2.0
        </footer>
      </main>

      {/* --------------------------------------------------------- */}
      {/* MODAL: AJOUTER / IMPORTER UN CV */}
      {/* --------------------------------------------------------- */}
      {showAddCVModal && (
        <div className="modal-backdrop" onClick={() => setShowAddCVModal(false)}>
          <div className="modal-window" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Ajouter un Candidat / CV</h3>
              <button className="btn-close" onClick={() => setShowAddCVModal(false)}>✕</button>
            </div>

            <div className="modal-tabs">
              <button
                className={`tab-btn ${cvTab === 'upload' ? 'active' : ''}`}
                onClick={() => setCvTab('upload')}
              >
                📁 Importer des fichiers (PDF, Word, TXT)
              </button>
              <button
                className={`tab-btn ${cvTab === 'manual' ? 'active' : ''}`}
                onClick={() => setCvTab('manual')}
              >
                ✍ Saisie manuelle / Copier-coller
              </button>
            </div>

            <div className="modal-body">
              {cvTab === 'upload' ? (
                <div className="upload-modal-zone">
                  <div className="upload-icon-lg">📄</div>
                  <h4>Sélectionnez un ou plusieurs CVs</h4>
                  <p>Formats supportés : <strong>PDF, Word (.docx), TXT, Markdown</strong></p>
                  <label className="btn-primary">
                    {uploadingCV ? '⏳ Analyse et extraction...' : 'Choisir les fichiers...'}
                    <input
                      type="file"
                      multiple
                      accept=".pdf,.docx,.doc,.txt,.md"
                      onChange={handleCVFilesUpload}
                      disabled={uploadingCV}
                      hidden
                    />
                  </label>
                </div>
              ) : (
                <form onSubmit={handleManualCVSubmit} className="manual-cv-form">
                  <div className="form-row">
                    <div className="form-group">
                      <label>Nom complet du candidat *</label>
                      <input
                        type="text"
                        required
                        placeholder="ex: Jean Dupont"
                        value={manualCV.name}
                        onChange={(e) => setManualCV({ ...manualCV, name: e.target.value })}
                      />
                    </div>
                    <div className="form-group">
                      <label>Titre / Rôle ciblé *</label>
                      <input
                        type="text"
                        required
                        placeholder="ex: Développeur Full Stack React / Node"
                        value={manualCV.title}
                        onChange={(e) => setManualCV({ ...manualCV, title: e.target.value })}
                      />
                    </div>
                  </div>

                  <div className="form-row">
                    <div className="form-group">
                      <label>Années d'expérience</label>
                      <input
                        type="number"
                        min="0"
                        max="40"
                        value={manualCV.experience_years}
                        onChange={(e) => setManualCV({ ...manualCV, experience_years: parseInt(e.target.value) || 0 })}
                      />
                    </div>
                    <div className="form-group">
                      <label>Email de contact</label>
                      <input
                        type="email"
                        placeholder="candidat@email.com"
                        value={manualCV.email}
                        onChange={(e) => setManualCV({ ...manualCV, email: e.target.value })}
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label>Compétences clés (séparées par des virgules)</label>
                    <input
                      type="text"
                      placeholder="ex: Python, React, Docker, PostgreSQL, AWS, CI/CD"
                      value={manualCV.skills}
                      onChange={(e) => setManualCV({ ...manualCV, skills: e.target.value })}
                    />
                  </div>

                  <div className="form-group">
                    <label>Résumé / Expérience / Texte complet du CV</label>
                    <textarea
                      rows="4"
                      placeholder="Collez ici le parcours, les expériences ou la description du CV..."
                      value={manualCV.raw_text}
                      onChange={(e) => setManualCV({ ...manualCV, raw_text: e.target.value })}
                    ></textarea>
                  </div>

                  <div className="modal-footer">
                    <button type="button" className="btn-secondary" onClick={() => setShowAddCVModal(false)}>
                      Annuler
                    </button>
                    <button type="submit" className="btn-primary" disabled={uploadingCV}>
                      {uploadingCV ? 'Enregistrement...' : 'Enregistrer le candidat'}
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      )}

      {/* --------------------------------------------------------- */}
      {/* MODAL: DETAIL MISSION */}
      {/* --------------------------------------------------------- */}
      {selectedMission && (
        <div className="modal-backdrop" onClick={() => setSelectedMission(null)}>
          <div className="modal-window lg" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <span className={`source-badge ${getPlatformClass(selectedMission.source)}`}>
                  {getPlatformDisplayName(selectedMission.source)}
                </span>
                <h3>{selectedMission.title}</h3>
              </div>
              <button className="btn-close" onClick={() => setSelectedMission(null)}>✕</button>
            </div>

            <div className="modal-body detail-body">
              <div className="mission-meta-bar">
                <div>🏢 <strong>Entreprise :</strong> {selectedMission.company || 'Client confidentiel'}</div>
                <div>📍 <strong>Lieu :</strong> {selectedMission.location || 'France / Télétravail'}</div>
                <div>💰 <strong>TJM / Tarif :</strong> {selectedMission.rate || 'Sur devis'}</div>
              </div>

              <h4>Compétences requises :</h4>
              <div className="skills-tags">
                {(selectedMission.skills || '').split(',').map((s, idx) => (
                  s.trim() && <span key={idx} className="skill-tag highlight">{s.trim()}</span>
                ))}
              </div>

              <h4>Description complète :</h4>
              <div className="mission-full-description">
                {selectedMission.description || 'Aucune description disponible.'}
              </div>
            </div>

            <div className="modal-footer">
              <button
                className="btn-match-action"
                onClick={() => {
                  setSelectedMission(null)
                  runMatchForMission(selectedMission.id)
                }}
              >
                🎯 Trouver le CV idéal pour cette offre
              </button>
              {selectedMission.url && (
                <a
                  href={selectedMission.url}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-primary"
                >
                  Voir sur le site officiel ↗
                </a>
              )}
            </div>
          </div>
        </div>
      )}

      {/* --------------------------------------------------------- */}
      {/* MODAL: DETAIL CANDIDAT */}
      {/* --------------------------------------------------------- */}
      {selectedCandidate && (
        <div className="modal-backdrop" onClick={() => setSelectedCandidate(null)}>
          <div className="modal-window" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="candidate-info">
                <div className="candidate-avatar">
                  {(selectedCandidate.name || 'C').substring(0, 2).toUpperCase()}
                </div>
                <div>
                  <h3>{selectedCandidate.name}</h3>
                  <span>{selectedCandidate.title}</span>
                </div>
              </div>
              <button className="btn-close" onClick={() => setSelectedCandidate(null)}>✕</button>
            </div>

            <div className="modal-body">
              <div className="candidate-contact">
                {selectedCandidate.email && <div>✉ Email : <strong>{selectedCandidate.email}</strong></div>}
                {selectedCandidate.phone && <div>📞 Téléphone : <strong>{selectedCandidate.phone}</strong></div>}
                <div>⏱ Expérience : <strong>{selectedCandidate.experience_years} ans</strong></div>
              </div>

              <h4>Compétences :</h4>
              <div className="skills-tags">
                {(selectedCandidate.skills || '').split(',').map((s, idx) => (
                  s.trim() && <span key={idx} className="skill-tag">{s.trim()}</span>
                ))}
              </div>

              {selectedCandidate.summary && (
                <>
                  <h4>Résumé :</h4>
                  <p>{selectedCandidate.summary}</p>
                </>
              )}

              {selectedCandidate.raw_text && (
                <>
                  <h4>Extrait du CV :</h4>
                  <div className="cv-raw-box">{selectedCandidate.raw_text.substring(0, 800)}...</div>
                </>
              )}
            </div>

            <div className="modal-footer">
              <button
                className="btn-match-action full"
                onClick={() => {
                  setSelectedCandidate(null)
                  runMatchForCV(selectedCandidate.id)
                }}
              >
                🎯 Trouver les meilleures offres pour ce profil
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
