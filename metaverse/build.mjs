// GitHub Pages용 docs/ 를 만듭니다.
// 사용법: node metaverse/build.mjs   (저장소 루트에서 실행)
//  - docs/index.html          ← metaverse/bonwon/index.html (본원초 메타버스, 첫 화면)
//  - docs/village/index.html  ← metaverse/index.html (우리마당, 아티팩트용 원본을 변환)
import { readFileSync, writeFileSync, mkdirSync, copyFileSync } from "node:fs";

// 1) 본원초 메타버스: 완성된 HTML 파일을 그대로 복사
mkdirSync("docs", { recursive: true });
copyFileSync("metaverse/bonwon/index.html", "docs/index.html");

// 2) 우리마당: 아티팩트용 본문 형식을 완전한 HTML 로 감싸기
const src = readFileSync("metaverse/index.html", "utf8");
const cut = src.indexOf('<div id="app">');
if (cut < 0) throw new Error('<div id="app"> 를 찾지 못했습니다');
const head = src.slice(0, cut).trim();
const body = src.slice(cut).trim().replace('import("./trystero-0.26.0.mjs")', 'import("../trystero-0.26.0.mjs")');
if (!body.includes('import("../trystero-0.26.0.mjs")')) throw new Error("trystero import 경로를 찾지 못했습니다");

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
mkdirSync("docs/village", { recursive: true });
writeFileSync("docs/village/index.html", html);

copyFileSync("metaverse/vendor/trystero-0.26.0.mjs", "docs/trystero-0.26.0.mjs");
copyFileSync("metaverse/vendor/trystero-LICENSE.txt", "docs/trystero-LICENSE.txt");
writeFileSync("docs/.nojekyll", "");
console.log("docs/ 생성 완료");
