# Показать структуру текущей папки
Write-Host "📁 ТЕКУЩАЯ СТРУКТУРА:" -ForegroundColor Yellow
Get-ChildItem -Recurse -Directory | ForEach-Object { $_.FullName.Replace($PWD.Path, "") } | Sort-Object

Write-Host "`n📄 ФАЙЛЫ В КОРНЕ:" -ForegroundColor Yellow
Get-ChildItem -File | Select-Object Name