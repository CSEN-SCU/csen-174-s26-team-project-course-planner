const fs = require("fs/promises");
const path = require("path");

const BULLETIN_ROOT = "https://www.scu.edu/bulletin/undergraduate/";
const COURSE_CODE_REGEX = /\b[A-Z]{2,5}\s?\d{1,3}[A-Z]?\b/g;
const STOP_WORDS = /(minor|certificate|laboratories|courses|faculty|research|program policies|master of)/i;
const URL_LIMIT = 450;
const BAD_SUBJECT_CODES = new Set(["GPA", "SAT", "ACT"]);

function normalizeWhitespace(text) {
  return text.replace(/\s+/g, " ").trim();
}

function stripHtml(html) {
  return normalizeWhitespace(
    html
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<[^>]+>/g, " ")
  );
}

function absoluteHref(href) {
  if (!href) return "";
  if (href.startsWith("http://") || href.startsWith("https://")) return href;
  if (href.startsWith("/")) return `https://www.scu.edu${href}`;
  return new URL(href, BULLETIN_ROOT).toString();
}

function uniqSorted(values) {
  return [...new Set(values)].sort();
}

function extractChapterUrls(indexHtml) {
  const links = indexHtml.match(/href="[^"]+"/g) || [];
  const urls = links
    .map((entry) => entry.replace(/^href="/, "").replace(/"$/, ""))
    .map(absoluteHref)
    .map((url) => url.split("#")[0])
    .filter((url) => url.includes("/bulletin/undergraduate/chapter-"))
    .filter((url) => url.endsWith(".html") || url.endsWith("/"));
  return uniqSorted(urls);
}

function extractInternalBulletinLinks(html) {
  const links = html.match(/href="[^"]+"/g) || [];
  const urls = links
    .map((entry) => entry.replace(/^href="/, "").replace(/"$/, ""))
    .map(absoluteHref)
    .filter((url) => url.startsWith(BULLETIN_ROOT))
    .filter((url) => url.endsWith(".html") || url.endsWith("/"))
    .map((url) => url.split("#")[0]);
  return uniqSorted(urls);
}

function decodeHtmlEntities(input) {
  return input
    .replace(/&amp;/g, "&")
    .replace(/&nbsp;/g, " ")
    .replace(/&#39;/g, "'")
    .replace(/&quot;/g, '"');
}

function cleanMajorName(raw) {
  return normalizeWhitespace(decodeHtmlEntities(raw).replace(/\s+/g, " "))
    .replace(/\s+\(.+?\)\s*$/g, "")
    .trim();
}

function toTitleCase(input) {
  return input
    .split(" ")
    .filter(Boolean)
    .map((word) => {
      if (["and", "of", "in", "or", "the"].includes(word.toLowerCase())) {
        return word.toLowerCase();
      }
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    })
    .join(" ")
    .replace(/\bw eb\b/gi, "Web");
}

function standardizeMajorName(raw) {
  const normalized = cleanMajorName(raw).replace(/\s+/g, " ");
  const match = normalized.match(
    /bachelor of (science|arts|fine arts)(?: degree)? in ([a-z&/\-\s]+?)(?: with| in addition| to qualify| students| must|,|\.|$)/i
  );
  if (!match) return "";
  const degree = `Bachelor of ${toTitleCase(match[1])}`;
  const majorTitle = toTitleCase(match[2].trim())
    .replace(/\bDegree\b/gi, "")
    .replace(/\bAt Scu.*$/gi, "")
    .replace(/\bA Field of\b/gi, "")
    .replace(/\bthe Engineering School\b/gi, "Engineering")
    .replace(/\s+/g, " ")
    .trim();
  if (
    /or the bachelor|with the following|to qualify|students|must complete|at scu|provide/i.test(
      majorTitle
    )
  ) {
    return "";
  }
  if (!majorTitle || majorTitle.length < 3) return "";
  return `${degree} in ${majorTitle}`;
}

function isLikelyCourseCode(course) {
  const normalized = course.replace(/\s+/g, " ").trim();
  const [subject] = normalized.split(" ");
  if (!subject || BAD_SUBJECT_CODES.has(subject)) return false;
  return true;
}

function parseMajorsFromText(html, sourceUrl) {
  const majors = [];
  const text = stripHtml(html);
  const majorMatcher =
    /Bachelor of (?:Science|Arts|Fine Arts)(?: degree)? in [A-Za-z&/\-\s]{3,100}/gi;
  let match;

  while ((match = majorMatcher.exec(text))) {
    const majorName = standardizeMajorName(match[0]);
    if (!majorName) continue;
    if (STOP_WORDS.test(majorName)) continue;
    if (majorName.includes("students majoring")) continue;
    const start = match.index;
    const windowText = text.slice(start, start + 5000);
    const rawCourses = windowText.match(COURSE_CODE_REGEX) || [];
    const courses = uniqSorted(
      rawCourses.map((course) => normalizeWhitespace(course)).filter(isLikelyCourseCode)
    );

    if (!courses.length) continue;
    majors.push({
      major: majorName,
      requiredCourses: courses,
      sourceUrl
    });
  }

  return majors;
}

function toCompactDb(majors) {
  const dictionary = [];
  const dictIndex = new Map();
  const records = majors.map((entry) => {
    const courseIndexes = entry.requiredCourses.map((course) => {
      if (!dictIndex.has(course)) {
        dictIndex.set(course, dictionary.length);
        dictionary.push(course);
      }
      return dictIndex.get(course);
    });
    return {
      m: entry.major,
      c: courseIndexes,
      s: entry.sourceUrl
    };
  });

  return {
    generatedAt: new Date().toISOString(),
    source: BULLETIN_ROOT,
    format: {
      m: "major name",
      c: "indexes into dictionary",
      s: "source url"
    },
    dictionary,
    records
  };
}

async function buildMajorsDb() {
  const indexResp = await fetch(BULLETIN_ROOT);
  if (!indexResp.ok) {
    throw new Error(`Failed to fetch bulletin index (${indexResp.status})`);
  }
  const indexHtml = await indexResp.text();
  const chapterUrls = extractChapterUrls(indexHtml);
  const queue = [...chapterUrls];
  const visited = new Set();
  const targetUrls = [];
  while (queue.length && targetUrls.length < URL_LIMIT) {
    const url = queue.shift();
    if (!url || visited.has(url)) continue;
    visited.add(url);
    targetUrls.push(url);

    try {
      const resp = await fetch(url);
      if (!resp.ok) continue;
      const html = await resp.text();
      const links = extractInternalBulletinLinks(html);
      for (const link of links) {
        if (!visited.has(link) && !queue.includes(link)) {
          queue.push(link);
        }
      }
    } catch {
      // Continue crawling other pages.
    }
  }

  const allMajors = [];
  for (const url of targetUrls) {
    const resp = await fetch(url);
    if (!resp.ok) {
      // Continue so one failed chapter does not block all.
      continue;
    }
    const html = await resp.text();
    const parsed = parseMajorsFromText(html, url);
    allMajors.push(...parsed);
  }

  const deduped = [];
  const seen = new Set();
  for (const entry of allMajors) {
    const key = entry.major.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    deduped.push(entry);
  }

  const compact = toCompactDb(deduped);
  const outDir = path.join(__dirname, "..", "data");
  const outPath = path.join(outDir, "majors.compact.json");
  await fs.mkdir(outDir, { recursive: true });
  await fs.writeFile(outPath, JSON.stringify(compact), "utf8");

  console.log(`Crawled ${targetUrls.length} bulletin pages`);
  console.log(
    `Wrote ${compact.records.length} majors with ${compact.dictionary.length} unique courses to ${outPath}`
  );
}

buildMajorsDb().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
