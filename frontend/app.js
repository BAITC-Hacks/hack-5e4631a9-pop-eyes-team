"use strict";

const form = document.querySelector("#recommendation-form");
const fields = document.querySelector("#request-fields");
const result = document.querySelector("#result");
const formStatus = document.querySelector("#form-status");
const retryOptions = document.querySelector("#retry-options");
const presetButtons = document.querySelector("#demo-presets");
const submitButton = form.querySelector("[type=submit]");
const money = new Intl.NumberFormat("ru-RU");
const labels = { city: "Город", date: "Дата", event_type: "Формат", category: "Категория", budget_kzt: "Бюджет", duration_hours: "Длительность", language: "Язык", preferences: "Пожелания" };
let optionsReady = false;
let submitting = false;

const presets = {
  business: { city: "Алматы", date: "2026-10-10", event_type: "корпоратив", category: "Ведущий", budget_kzt: "1000000", preferences: "Деловой корпоратив: в первую очередь опыт деловых мероприятий и интеллигентный юмор. Без навязчивых конкурсов." },
  informal: { city: "Алматы", date: "2026-10-10", event_type: "корпоратив", category: "Ведущий", budget_kzt: "1000000", preferences: "Неформальный корпоратив: главный акцент на развлечениях и танцах, без долгих речей и наставлений." },
  december: { city: "Алматы", date: "2026-12-19", event_type: "корпоратив", category: "Ведущий", budget_kzt: "1000000", preferences: "Деловой корпоратив для IT-команды: интеллигентный юмор." },
  florist: { city: "Алматы", date: "2026-10-10", event_type: "корпоратив", category: "Флорист", budget_kzt: "500000", preferences: "Сдержанное оформление корпоративного вечера." },
  low_budget: { city: "Алматы", date: "2026-10-10", event_type: "корпоратив", category: "Ведущий", budget_kzt: "10000", preferences: "" },
  absent: { city: "Астана", date: "2026-10-10", event_type: "корпоратив", category: "Декоратор", budget_kzt: "1000000", preferences: "" }
};

function node(tag, className, value) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (value !== undefined) item.textContent = String(value);
  return item;
}

async function api(path, init = {}) {
  let response;
  try {
    response = await fetch(path, { ...init, signal: AbortSignal.timeout(45000) });
  } catch (error) {
    throw new Error(error.name === "TimeoutError" ? "Сервер не ответил вовремя. Повторите запрос." : "Не удалось связаться с сервером. Проверьте соединение и повторите запрос.");
  }
  let data;
  try { data = await response.json(); }
  catch { throw new Error("Сервер вернул неожиданный ответ. Повторите запрос позже."); }
  if (!response.ok) {
    if (response.status === 422 && Array.isArray(data.detail)) {
      throw new Error(data.detail.map((e) => `${labels[e.loc?.[1]] || "Поле"}: ${e.msg}`).join(" "));
    }
    throw new Error(data.detail?.message || "Сервис временно недоступен. Повторите запрос позже.");
  }
  return data;
}

function fillSelect(name, values, preferred, optional = false) {
  const select = form.elements.namedItem(name);
  const previous = select.value || preferred;
  select.replaceChildren();
  if (optional) select.append(new Option("Не важно", ""));
  values.forEach((value) => select.append(new Option(value, value)));
  if (values.includes(previous)) select.value = previous;
  else if (optional) select.value = "";
}

async function loadOptions() {
  optionsReady = false;
  fields.disabled = true;
  retryOptions.hidden = true;
  formStatus.textContent = "Загружаем параметры из каталога…";
  formStatus.className = "hint";
  try {
    const options = await api("/api/options");
    fillSelect("city", options.cities, "Алматы");
    fillSelect("category", options.categories, "Ведущий");
    fillSelect("event_type", options.event_types, "корпоратив");
    fillSelect("language", options.languages, "", true);
    const dateInput = form.elements.namedItem("date");
    dateInput.min = options.date_min;
    dateInput.max = options.date_max;
    const initialDate = dateInput.value || "2026-10-10";
    dateInput.value = initialDate < options.date_min ? options.date_min : initialDate > options.date_max ? options.date_max : initialDate;
    const displayDate = (value) => value.split("-").reverse().join(".");
    document.querySelector("#calendar-note").textContent = `Доступность известна с ${displayDate(options.date_min)} по ${displayDate(options.date_max)} включительно.`;
    formStatus.textContent = "Параметры загружены из каталога.";
    optionsReady = true;
    fields.disabled = false;
  } catch (error) {
    formStatus.textContent = error.message;
    formStatus.className = "hint error";
    retryOptions.hidden = false;
  }
}

function buildRequest(formElement) {
  const data = new FormData(formElement);
  return {
    city: data.get("city"), date: data.get("date"), event_type: data.get("event_type"),
    category: data.get("category"), budget_kzt: Number(data.get("budget_kzt")),
    duration_hours: data.get("duration_hours") ? Number(data.get("duration_hours")) : null,
    language: data.get("language") || null,
    preferences: String(data.get("preferences") || "").trim()
  };
}

function applyPreset(name) {
  const preset = presets[name];
  if (!optionsReady || !preset || submitting) return;
  for (const key of ["city", "event_type", "category"]) {
    const select = form.elements.namedItem(key);
    if (![...select.options].some((option) => option.value === preset[key])) {
      formStatus.textContent = "Этот готовый запрос недоступен в текущем каталоге.";
      formStatus.className = "hint error";
      return;
    }
  }
  const date = form.elements.namedItem("date");
  if (preset.date < date.min || preset.date > date.max) {
    formStatus.textContent = "Дата готового запроса находится вне календаря каталога.";
    formStatus.className = "hint error";
    return;
  }
  for (const [key, value] of Object.entries(preset)) form.elements.namedItem(key).value = value;
  form.elements.namedItem("duration_hours").value = "";
  form.elements.namedItem("language").value = "";
  formStatus.textContent = "Готовый запрос заполнен. Нажмите «Подобрать подрядчиков».";
  formStatus.className = "hint";
  result.className = "placeholder";
  result.replaceChildren(node("p", "", "Условия изменены. Нажмите кнопку, чтобы получить новый результат."));
}

function renderCard(card) {
  const article = node("article", "card");
  const top = node("div", "card-top");
  top.append(node("span", "category", card.categories.join(" · ")), node("span", "muted", card.city));
  article.append(top, node("h4", "", card.name), node("p", "card-reason", card.reason));
  const flags = [];
  if (card.synthetic) flags.push("Синтетический профиль");
  if (card.city_imputed) flags.push("Город подставлен в датасете");
  if (card.price_imputed) flags.push("Цена подставлена в датасете");
  if (flags.length) article.append(node("p", "data-flags", flags.join(" · ")));
  const bottom = node("div", "card-bottom");
  bottom.append(node("strong", "", `от ${money.format(card.price_from_kzt)} ₸`), node("span", "muted", card.id));
  article.append(bottom);
  return article;
}

function renderResponse(response) {
  result.replaceChildren();
  result.className = "result";
  const summary = node("div", "summary");
  const title = response.status === "matched" ? "Есть варианты для вас" : response.status === "category_absent" ? "Категории пока нет" : "Подходящих вариантов нет";
  summary.append(node("h3", "", title), node("p", "", response.message));
  result.append(summary);
  const exclusionLabels = { date: "заняты на дату", budget: "выше бюджета", event_type: "другой формат", duration: "не подходят по длительности", language: "другой язык" };
  const exclusions = Object.entries(response.excluded_counts).filter(([, count]) => count > 0).map(([key, count]) => `${exclusionLabels[key]} — ${count}`);
  if (exclusions.length) result.append(node("p", "hint", `Исключены: ${exclusions.join("; ")}. Каждый кандидат учтён один раз.`));
  if (response.status !== "matched") {
    result.append(node("p", "hint", response.status === "category_absent" ? "Попробуйте выбрать другой город или категорию." : "Попробуйте изменить дату, бюджет или другие обязательные условия."));
    return;
  }
  const meta = node("div", "result-meta");
  meta.append(node("span", response.selection_mode === "fallback" ? "mode fallback" : "mode", response.selection_mode === "fallback" ? "Резервный подбор · без AI" : "AI-подбор"));
  meta.append(node("span", "muted", `Показано ${response.cards.length} из ${response.eligible_count} подходящих`));
  result.append(meta);
  const list = node("div", "cards");
  response.cards.forEach((card) => list.append(renderCard(card)));
  result.append(list);
  if (response.cards.length < 3) result.append(node("p", "hint", `Карточек меньше трёх: условиям соответствуют только ${response.eligible_count}.`));
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!optionsReady || submitting || !form.reportValidity()) return;
  const request = buildRequest(form);
  submitting = true;
  fields.disabled = true;
  submitButton.textContent = "Подбираем…";
  result.className = "placeholder";
  result.setAttribute("aria-busy", "true");
  result.replaceChildren(node("p", "", "Проверяем условия и выбираем подходящих подрядчиков…"));
  try {
    renderResponse(await api("/api/recommendations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request) }));
  } catch (error) {
    result.className = "placeholder error";
    result.replaceChildren(node("p", "", error.message));
  } finally {
    submitting = false;
    fields.disabled = false;
    submitButton.textContent = "Подобрать подрядчиков →";
    result.setAttribute("aria-busy", "false");
  }
});

retryOptions.addEventListener("click", loadOptions);
presetButtons.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-preset]");
  if (button) applyPreset(button.dataset.preset);
});
loadOptions();
