# 無界塾八年級專案課：生活科技與結構＿椅子

給家長看的學生作品展。網站是靜態頁面，之後部署到 GitHub Pages。

家長流程：打開網站 → 讀課程理念 → 選 A / B / C 班或搜尋姓名 → 點學生卡片 → 在頁面內預覽 Google 簡報或 Canva。

## 本機預覽

在專案根目錄執行：

```bash
python3 -m http.server 8080
```

瀏覽器打開：<http://localhost:8080>

檔案必須透過本機伺服器開啟，直接雙擊 `index.html` 時，瀏覽器可能擋掉 `data/students.json`。

## 更新學生名單

只需要改 [`data/students.json`](data/students.json)。每位學生一筆：

```json
{
  "A": [
    {
      "id": "a1",
      "name": "王小明",
      "projectUrl": "https://docs.google.com/presentation/d/XXXX/edit?usp=sharing",
      "thumbUrl": "assets/thumbs/a1.jpg"
    }
  ]
}
```

注意：

- `id` 在同班內不要重複
- `name` 會顯示在卡片上，也是搜尋用的名字
- `projectUrl` 貼 Google 簡報或 Canva 的分享連結
- 連結權限請設成 **知道連結的任何人 · 檢視者**，否則家長會看到登入畫面或空白預覽
- 還沒交作品的學生，`projectUrl` 可先留空字串 `""`

封面預覽圖放在 `assets/thumbs/`。新增或更換連結後，可重跑：

```bash
python3 tools/capture-thumbs.py
```

這會抓 Google 簡報第一頁匯出圖，並對 Canva 封面截圖後寫回 `thumbUrl`。

課程理念文案直接改 [`index.html`](index.html) 裡「課程設計理念」那一段即可。

## 部署到 GitHub Pages

1. 在 GitHub 建立新的 **Public** repository（例如 `bts-grade8-chairs`）
2. 不要勾選「Add a README file」
3. 把這個資料夾裡的檔案推上去，確定 `index.html` 在 repo **根目錄**

```bash
git init
git add index.html styles.css js data assets README.md tools .nojekyll
git commit -m "Add grade 8 chair showcase"
git branch -M main
git remote add origin https://github.com/<你的帳號>/<repo名稱>.git
git push -u origin main
```

4. 打開 repo → **Settings** → **Pages**
5. Source 選 **Deploy from a branch**
6. Branch 選 `main`，資料夾選 `/ (root)`，按 Save
7. 等 1–2 分鐘，網址會是：

```
https://<你的帳號>.github.io/<repo名稱>/
```

之後只要改 `data/students.json`（或理念文案）再 `git push`，網站就會更新。

## 檔案說明

```
bts_project_grade8/
├── index.html           頁面結構與課程理念
├── styles.css           外觀
├── js/app.js            班級切換、搜尋、卡片、內嵌預覽
├── data/students.json   學生姓名、作品連結、封面圖路徑
├── assets/thumbs/       每位學生的封面截圖
├── tools/capture-thumbs.py  重新擷取封面圖
├── .nojekyll            讓 GitHub Pages 不要走 Jekyll
└── README.md            本說明
```
