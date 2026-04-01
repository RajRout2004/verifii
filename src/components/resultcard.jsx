export default function ResultCard({ result }) {
  const { verdict, gst_data, web_data } = result

  const verdictConfig = {
    GREEN:  { bg: 'bg-emerald-900/40', border: 'border-emerald-600', text: 'text-emerald-400', bar: 'bg-emerald-500', label: 'Low Risk',    emoji: '✅' },
    YELLOW: { bg: 'bg-yellow-900/40',  border: 'border-yellow-600',  text: 'text-yellow-400',  bar: 'bg-yellow-500',  label: 'Medium Risk', emoji: '⚠️' },
    RED:    { bg: 'bg-red-900/40',     border: 'border-red-600',     text: 'text-red-400',     bar: 'bg-red-500',     label: 'High Risk',   emoji: '🚨' },
  }
  const config = verdictConfig[verdict?.verdict] || verdictConfig.YELLOW

  const Section = ({ title, children }) => (
    <div className="p-4 bg-slate-800 rounded-xl border border-slate-700">
      <p className="text-xs text-slate-500 mb-3 uppercase tracking-widest font-medium">{title}</p>
      {children}
    </div>
  )

  const Badge = ({ text, color }) => {
    const colors = {
      green:  'bg-emerald-900/50 text-emerald-400 border-emerald-700',
      red:    'bg-red-900/50 text-red-400 border-red-700',
      yellow: 'bg-yellow-900/50 text-yellow-400 border-yellow-700',
      gray:   'bg-slate-700 text-slate-300 border-slate-600',
      blue:   'bg-blue-900/50 text-blue-400 border-blue-700',
    }
    return (
      <span className={`text-xs font-medium px-2 py-1 rounded-full border ${colors[color] || colors.gray}`}>
        {text}
      </span>
    )
  }

  const SourceRow = ({ label, status, detail }) => {
    const statusConfig = {
      found:     { text: '✓ Found',     color: 'text-emerald-400' },
      clean:     { text: '✓ Clean',     color: 'text-emerald-400' },
      flagged:   { text: '⚠ Flagged',   color: 'text-yellow-400' },
      not_found: { text: '✗ Not found', color: 'text-red-400' },
      skipped:   { text: '— Not checked', color: 'text-slate-500' },
    }
    const cfg = statusConfig[status] || statusConfig.not_found
    return (
      <div className="flex items-center justify-between py-1.5 border-b border-slate-700/50 last:border-0">
        <span className="text-slate-400 text-xs">{label}</span>
        <div className="flex items-center gap-2">
          {detail && <span className="text-slate-500 text-xs">{detail}</span>}
          <span className={`text-xs font-medium ${cfg.color}`}>
            {cfg.text}
          </span>
        </div>
      </div>
    )
  }

  const google_fraud      = web_data?.google_fraud || {}
  const google_complaints = web_data?.google_complaints || {}
  const indiamart         = web_data?.indiamart || {}
  const tradeindia        = web_data?.tradeindia || {}
  const justdial          = web_data?.justdial || {}
  const mca               = web_data?.mca || {}
  const linkedin          = web_data?.linkedin || {}
  const website           = web_data?.website || {}
  const email_check       = web_data?.email_check || {}
  const scam_check        = web_data?.scam_check || {}
  const zauba             = web_data?.zauba || {}

  // Determine if GST was actually checked
  // For company name searches: gst_data has search_type='company_name' with gstin_count
  // For GSTIN searches: gst_data has 'valid' field
  const isCompanySearch = gst_data?.search_type === 'company_name'
  const gstWasChecked = gst_data && Object.keys(gst_data).length > 0
  let gstStatus, gstDetail
  if (isCompanySearch) {
    const count = gst_data?.gstin_count || 0
    gstStatus = count > 0 ? 'found' : 'not_found'
    gstDetail = count > 0 ? `${count} GSTIN${count > 1 ? 's' : ''} found` : null
  } else if (gstWasChecked) {
    gstStatus = gst_data?.valid ? 'found' : 'not_found'
    gstDetail = gst_data?.status || null
  } else {
    gstStatus = 'skipped'
    gstDetail = null
  }

  // Scam/fraud/complaint statuses — invert the logic so it makes sense
  const scamStatus = !scam_check?.risk_level ? 'skipped'
    : scam_check.risk_level === 'LOW' ? 'clean'
    : 'flagged'
  const fraudStatus = google_fraud?.fraud_mentions > 0 ? 'flagged' : 'clean'
  const complaintStatus = google_complaints?.complaint_count > 0 ? 'flagged' : 'clean'

  // Website status — handle discovered websites and explicitly provided websites
  const websiteStatus = website?.not_discovered ? 'not_found'
    : website?.url ? (website?.accessible ? 'found' : 'not_found')
    : website?.accessible ? 'found'
    : 'not_found'

  const scamRiskColor = { HIGH: 'red', MEDIUM: 'yellow', LOW: 'green', UNKNOWN: 'gray' }

  return (
    <div className="mt-8 space-y-4">

      {/* Trust Score */}
      <div className={`p-5 rounded-xl border ${config.bg} ${config.border}`}>
        <div className="flex items-center justify-between mb-3">
          <div>
            <p className="text-slate-400 text-xs mb-1">Trust Score</p>
            <p className={`text-4xl font-bold ${config.text}`}>
              {verdict?.trust_score}
              <span className="text-lg font-normal text-slate-500">/100</span>
            </p>
          </div>
          <div className="text-right">
            <span className="text-2xl">{config.emoji}</span>
            <p className={`text-sm font-semibold mt-1 ${config.text}`}>{config.label}</p>
          </div>
        </div>
        <div className="w-full bg-slate-700 rounded-full h-2">
          <div className={`h-2 rounded-full transition-all duration-700 ${config.bar}`}
            style={{ width: `${verdict?.trust_score}%` }} />
        </div>
      </div>

      {/* Summary */}
      <Section title="Summary">
        <p className="text-slate-200 text-sm leading-relaxed">{verdict?.summary}</p>
      </Section>

      {/* Red Flags + Positive Signals */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {verdict?.red_flags?.length > 0 && (
          <div className="p-4 bg-red-900/20 rounded-xl border border-red-800/50">
            <p className="text-xs text-red-400 mb-3 uppercase tracking-widest font-medium">Red Flags</p>
            <ul className="space-y-2">
              {verdict.red_flags.map((f, i) => (
                <li key={i} className="flex gap-2 text-sm text-red-300">
                  <span className="mt-0.5 shrink-0">🚩</span><span>{f}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {verdict?.positive_signals?.length > 0 && (
          <div className="p-4 bg-emerald-900/20 rounded-xl border border-emerald-800/50">
            <p className="text-xs text-emerald-400 mb-3 uppercase tracking-widest font-medium">Positive Signals</p>
            <ul className="space-y-2">
              {verdict.positive_signals.map((s, i) => (
                <li key={i} className="flex gap-2 text-sm text-emerald-300">
                  <span className="mt-0.5 shrink-0">✅</span><span>{s}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Detailed Reasons */}
      <Section title="Detailed Reasons">
        <ul className="space-y-2">
          {verdict?.reasons?.map((r, i) => (
            <li key={i} className="flex gap-2 text-sm text-slate-300">
              <span className="text-indigo-400 mt-0.5 shrink-0">•</span><span>{r}</span>
            </li>
          ))}
        </ul>
      </Section>

      {/* Recommendation */}
      <div className="p-4 bg-indigo-900/30 rounded-xl border border-indigo-700/50">
        <p className="text-xs text-indigo-400 mb-1 uppercase tracking-widest font-medium">Recommendation</p>
        <p className="text-slate-200 text-sm leading-relaxed">{verdict?.recommendation}</p>
      </div>

      {/* Research Coverage Overview */}
      <Section title="Research Coverage">
        <div className="space-y-0">
          <SourceRow label="GST Registry"     status={gstStatus}                                 detail={gstDetail} />
          <SourceRow label="MCA Portal"       status={mca?.found ? 'found' : 'not_found'}        detail={mca?.companies?.[0]?.status} />
          <SourceRow label="IndiaMART"        status={indiamart?.found ? 'found' : 'not_found'}  detail={indiamart?.verified_count > 0 ? `${indiamart.verified_count} verified` : null} />
          <SourceRow label="TradeIndia"       status={tradeindia?.found ? 'found' : 'not_found'} detail={tradeindia?.verified_count > 0 ? `${tradeindia.verified_count} verified` : null} />
          <SourceRow label="Justdial"         status={justdial?.found ? 'found' : 'not_found'}   detail={justdial?.ratings?.[0]} />
          <SourceRow label="Zauba Corp"       status={zauba?.found ? 'found' : 'not_found'} />
          <SourceRow label="LinkedIn"         status={linkedin?.profile_found ? 'found' : 'not_found'} />
          <SourceRow label="Website"          status={websiteStatus}                              detail={website?.domain_age_years ? `${website.domain_age_years}yr domain` : null} />
          <SourceRow label="Scam Databases"   status={scamStatus}                                 detail={scam_check?.risk_level ? `Risk: ${scam_check.risk_level}` : null} />
          <SourceRow label="Fraud Search"     status={fraudStatus}                                detail={google_fraud?.fraud_mentions > 0 ? `${google_fraud.fraud_mentions} mentions` : null} />
          <SourceRow label="Complaint Search" status={complaintStatus}                            detail={google_complaints?.complaint_count > 0 ? `${google_complaints.complaint_count} found` : null} />
        </div>
      </Section>

      {/* GST Data */}
      {gst_data?.valid && (
        <Section title="GST Registry Data">
          <div className="grid grid-cols-2 gap-3 text-sm">
            {[
              ['Legal Name',  gst_data.legal_name],
              ['Trade Name',  gst_data.trade_name],
              ['Status',      gst_data.status],
              ['State',       gst_data.state],
              ['Reg. Date',   gst_data.registration_date],
              ['Type',        gst_data.business_type],
              ['Source',      gst_data.source],
            ].map(([label, value]) => value && value !== 'N/A' ? (
              <div key={label}>
                <p className="text-slate-500 text-xs">{label}</p>
                <p className="text-slate-200">{value}</p>
              </div>
            ) : null)}
          </div>
        </Section>
      )}

      {/* GSTIN Summary for company name searches */}
      {isCompanySearch && gst_data?.gstin_count > 0 && (
        <Section title="GSTIN Registry Data">
          <p className="text-slate-400 text-xs mb-3">
            Found {gst_data.gstin_count} GSTIN registration{gst_data.gstin_count > 1 ? 's' : ''} across India
          </p>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {gst_data.gstins_found?.slice(0, 8).map((item, i) => (
              <div key={i} className="flex items-center justify-between py-1.5 border-b border-slate-700/50 last:border-0">
                <div>
                  <p className="text-white text-xs font-mono">{item.gstin}</p>
                  <p className="text-slate-500 text-xs">{item.state}</p>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  item.status?.toLowerCase().includes('active')
                    ? 'bg-emerald-900/50 text-emerald-400'
                    : 'bg-slate-700 text-slate-400'
                }`}>
                  {item.status || 'Found'}
                </span>
              </div>
            ))}
          </div>
          {gst_data.gstin_count > 8 && (
            <p className="text-slate-500 text-xs mt-2">+ {gst_data.gstin_count - 8} more GSTINs found</p>
          )}
        </Section>
      )}

      {/* MCA Data */}
      {mca?.found && mca.companies?.[0] && (
        <Section title="MCA Company Data">
          <div className="grid grid-cols-2 gap-3 text-sm">
            {[
              ['Company Name',       mca.companies[0].name],
              ['CIN',                mca.companies[0].cin],
              ['Status',             mca.companies[0].status],
              ['Incorporation Date', mca.companies[0].incorporation_date],
              ['Type',               mca.companies[0].type],
              ['State',              mca.companies[0].state],
            ].map(([label, value]) => value && value !== 'N/A' ? (
              <div key={label}>
                <p className="text-slate-500 text-xs">{label}</p>
                <p className="text-slate-200">{value}</p>
              </div>
            ) : null)}
          </div>
        </Section>
      )}

      {/* Website Analysis */}
      {website?.url && (
        <Section title="Website Analysis">
          <div className="flex flex-wrap gap-2 mb-3">
            <Badge text={website.accessible ? 'Accessible' : 'Not Accessible'}       color={website.accessible ? 'green' : 'red'} />
            <Badge text={website.has_professional_domain ? 'Pro Domain' : 'Free Domain'} color={website.has_professional_domain ? 'green' : 'red'} />
            <Badge text={website.has_contact_info ? 'Has Contact' : 'No Contact'}    color={website.has_contact_info ? 'green' : 'red'} />
            <Badge text={website.has_address ? 'Has Address' : 'No Address'}         color={website.has_address ? 'green' : 'yellow'} />
            {website.domain_age_years != null && (
              <Badge
                text={`Domain: ${website.domain_age_years}yr`}
                color={website.domain_age_years >= 3 ? 'green' : website.domain_age_years >= 1 ? 'yellow' : 'red'}
              />
            )}
          </div>
          {website.flags?.length > 0 && (
            <ul className="space-y-1 mt-2">
              {website.flags.map((f, i) => (
                <li key={i} className="text-xs text-yellow-400 flex gap-1"><span>⚠</span><span>{f}</span></li>
              ))}
            </ul>
          )}
        </Section>
      )}

      {/* Email Check */}
      {email_check?.email && (
        <Section title="Email Domain Check">
          <div className="flex items-center gap-3">
            <Badge
              text={email_check.is_professional ? 'Professional Email' : 'Free Email — Red Flag'}
              color={email_check.is_professional ? 'green' : 'red'}
            />
            <span className="text-slate-400 text-xs">{email_check.email}</span>
          </div>
        </Section>
      )}

      {/* Scam Check */}
      {scam_check?.risk_level && (
        <Section title="Scam / Blacklist Check">
          <div className="flex items-center gap-3 mb-2">
            <Badge text={`Risk: ${scam_check.risk_level}`} color={scamRiskColor[scam_check.risk_level] || 'gray'} />
            <span className="text-slate-500 text-xs">{scam_check.fraud_flags} fraud signal(s) detected</span>
          </div>
          {scam_check.flagged_snippets?.length > 0 && (
            <ul className="space-y-1 mt-2">
              {scam_check.flagged_snippets.map((s, i) => (
                <li key={i} className="text-xs text-red-300 bg-red-900/20 p-2 rounded-lg">{s.slice(0, 140)}...</li>
              ))}
            </ul>
          )}
        </Section>
      )}

      {/* B2B Marketplaces */}
      {(indiamart?.found || tradeindia?.found || justdial?.found) && (
        <Section title="B2B Marketplace Listings">
          <div className="space-y-3">
            {indiamart?.found && (
              <div>
                <p className="text-slate-400 text-xs font-medium mb-1">IndiaMART</p>
                <div className="flex flex-wrap gap-1">
                  {indiamart.companies_found?.map((c, i) => <Badge key={i} text={c} color="blue" />)}
                  {indiamart.verified_count > 0 && <Badge text={`${indiamart.verified_count} verified`} color="green" />}
                </div>
              </div>
            )}
            {tradeindia?.found && (
              <div>
                <p className="text-slate-400 text-xs font-medium mb-1">TradeIndia</p>
                <div className="flex flex-wrap gap-1">
                  {tradeindia.companies_found?.map((c, i) => <Badge key={i} text={c} color="blue" />)}
                  {tradeindia.verified_count > 0 && <Badge text={`${tradeindia.verified_count} verified`} color="green" />}
                </div>
              </div>
            )}
            {justdial?.found && (
              <div>
                <p className="text-slate-400 text-xs font-medium mb-1">Justdial</p>
                <div className="flex flex-wrap gap-1">
                  {justdial.businesses_found?.map((b, i) => <Badge key={i} text={b} color="blue" />)}
                </div>
              </div>
            )}
          </div>
        </Section>
      )}

    </div>
  )
}