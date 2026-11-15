// 아티팩트용 metaverse/index.html 을 GitHub Pages용 docs/ 로 변환합니다.
// 사용법: node metaverse/build.mjs   (저장소 루트에서 실행)
import { readFileSync, writeFileSync, mkdirSync, copyFileSync } from "node:fs";

const src = readFileSync("metaverse/index.html", "utf8");
const cut = src.indexOf('<div id="app">');
if (cut < 0) throw new Error('<div id="app"> 를 찾지 못했습니다');
const head = src.slice(0, cut).trim();
const body = src.slice(cut).trim();

const html = `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
${head}
</head>
<body>
${body}
</body>
</html>
`;

mkdirSync("docs", { recursive: true });
writeFileSync("docs/index.html", html);
copyFileSync("metaverse/vendor/trystero-0.26.0.mjs", "docs/trystero-0.26.0.mjs");
copyFileSync("metaverse/vendor/trystero-LICENSE.txt", "docs/trystero-LICENSE.txt");
writeFileSync("docs/.nojekyll", "");
console.log("docs/ 생성 완료");
