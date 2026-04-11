param()

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$utcNow = (Get-Date).ToUniversalTime()
$timestamp = $utcNow.ToString('yyyyMMddTHHmmssZ')
$bundleRoot = Join-Path $repoRoot ('local_untracked\package_lane_' + $timestamp)
$sourceRoot = Join-Path $bundleRoot 'sources'

New-Item -ItemType Directory -Path $sourceRoot -Force | Out-Null

$files = @(
    'deliverables/DATA780/BLIND_ML_FINAL_WRITEUP.md',
    'deliverables/DATA740/BLIND_ML_ETHICAL_ANALYSIS_REPORT.md',
    'deliverables/DATA780/README.md',
    'deliverables/DATA740/README.md',
    'docs/reports/INDEX.md',
    'docs/reports/reference/GENERATED_REPORT_SURFACES.md',
    'docs/reports/validations/INDEX.md',
    'local_untracked/reports/CALAMUM_D2_CANONICAL_DATASET_AUTHORITY_LOCK_PACKET_20260411.md',
    'local_untracked/reports/CALAMUM_D3_CANONICAL_DS_REGENERATION_PACKET_20260411.md',
    'local_untracked/reports/CALAMUM_D4_CANONICAL_REPORT_AND_FIGURE_REGENERATION_PACKET_20260411.md',
    'local_untracked/reports/CALAMUM_CANONICAL_DS_REGENERATION_AND_SUBMISSION_PLAN_20260410.md',
    'planning/CALAMUM_FINAL_REPORT_PRIORITY_STACK_20260409.md'
)

$copied = @()
$missing = @()
$checksums = @()

foreach ($relativePath in $files) {
    $sourcePath = Join-Path $repoRoot $relativePath
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        $missing += $relativePath
        continue
    }

    $destinationPath = Join-Path $sourceRoot $relativePath
    $destinationDir = Split-Path -Parent $destinationPath
    New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
    Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Force
    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $sourcePath
    $checksums += [PSCustomObject]@{
        path = $relativePath
        sha256 = $hash.Hash.ToLowerInvariant()
    }
    $copied += $relativePath
}

$collectionRoot = Join-Path $repoRoot 'docs/reports/collections/liv-r8bc9'
if (Test-Path -LiteralPath $collectionRoot) {
    $destinationCollectionRoot = Join-Path $sourceRoot 'docs/reports/collections/liv-r8bc9'
    New-Item -ItemType Directory -Path (Split-Path -Parent $destinationCollectionRoot) -Force | Out-Null
    Copy-Item -LiteralPath $collectionRoot -Destination $destinationCollectionRoot -Recurse -Force
    $collectionFiles = Get-ChildItem -LiteralPath $collectionRoot -Recurse -File | Sort-Object FullName
    foreach ($file in $collectionFiles) {
        $relativePath = $file.FullName.Substring($repoRoot.Length + 1).Replace('\','/')
        $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName
        $checksums += [PSCustomObject]@{
            path = $relativePath
            sha256 = $hash.Hash.ToLowerInvariant()
        }
    }
}
else {
    $missing += 'docs/reports/collections/liv-r8bc9/'
}

$manifest = [PSCustomObject]@{
    package_lane = 'v1 ship/package closeout'
    created_at_utc = $utcNow.ToString('o')
    bundle_root = $bundleRoot.Substring($repoRoot.Length + 1).Replace('\','/')
    sources_root = ($sourceRoot.Substring($repoRoot.Length + 1).Replace('\','/'))
    zip_path = ('local_untracked/' + (Split-Path -Leaf $bundleRoot) + '.zip')
    authority_basis = @(
        'local_untracked/reports/CALAMUM_D2_CANONICAL_DATASET_AUTHORITY_LOCK_PACKET_20260411.md',
        'local_untracked/reports/CALAMUM_D3_CANONICAL_DS_REGENERATION_PACKET_20260411.md',
        'local_untracked/reports/CALAMUM_D4_CANONICAL_REPORT_AND_FIGURE_REGENERATION_PACKET_20260411.md',
        'local_untracked/reports/CALAMUM_CANONICAL_DS_REGENERATION_AND_SUBMISSION_PLAN_20260410.md',
        'planning/CALAMUM_FINAL_REPORT_PRIORITY_STACK_20260409.md'
    )
    primary_submission_sources = @(
        'deliverables/DATA780/BLIND_ML_FINAL_WRITEUP.md',
        'deliverables/DATA740/BLIND_ML_ETHICAL_ANALYSIS_REPORT.md'
    )
    deferred_work_gates = @(
        'full pipeline has run successfully end-to-end',
        'honeypot-ready TV-0/TV-3-labeled dataset exists as active authority'
    )
    pdf_renderer_available = $false
    note = 'Source package emitted successfully; PDF/docx rendering remains a separate operator step because no PDF export toolchain is installed in this environment.'
    copied_files = $copied
    missing_entries = $missing
    checksums = $checksums
}

$manifestPath = Join-Path $bundleRoot 'PACKAGE_MANIFEST.json'
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8

$readmeLines = @(
    '# v1 Package Lane Bundle',
    '',
    '- Package lane: `v1 ship/package closeout`',
    ('- Created at (UTC): `' + $utcNow.ToString('o') + '`'),
    '- Purpose: bounded source bundle for the active v1 package lane using the closed D2-D6 authority chain.',
    '- Renderer status: no PDF/docx export toolchain was available in this environment during packaging.',
    '- Included primary submission sources:',
    '  - `deliverables/DATA780/BLIND_ML_FINAL_WRITEUP.md`',
    '  - `deliverables/DATA740/BLIND_ML_ETHICAL_ANALYSIS_REPORT.md`',
    '- Included tracked report family: `docs/reports/collections/liv-r8bc9/`',
    '- Deferred work gates before DATA7** reopens:',
    '  - full pipeline has run successfully end-to-end',
    '  - honeypot-ready `TV-0` / `TV-3`-labeled dataset exists as active authority',
    '',
    'See `PACKAGE_MANIFEST.json` for the copied file list and SHA256 checksums.'
)
$readmePath = Join-Path $bundleRoot 'README.md'
$readmeLines | Set-Content -LiteralPath $readmePath -Encoding utf8

$zipPath = $bundleRoot + '.zip'
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path (Join-Path $bundleRoot '*') -DestinationPath $zipPath -Force

$result = [PSCustomObject]@{
    bundle_root = $bundleRoot.Substring($repoRoot.Length + 1).Replace('\','/')
    zip_path = $zipPath.Substring($repoRoot.Length + 1).Replace('\','/')
    copied_count = $copied.Count
    missing_count = $missing.Count
    missing_entries = $missing
    manifest_path = $manifestPath.Substring($repoRoot.Length + 1).Replace('\','/')
    readme_path = $readmePath.Substring($repoRoot.Length + 1).Replace('\','/')
}

$result | ConvertTo-Json -Depth 5
