"use strict";

// Только примеры отображения. Реальные карточки придут из API на втором часу.
const examples = {
  matched: {
    status: "matched", message: "Нашли подходящих подрядчиков. Сравните объяснения и выберите, кого обсудить подробнее.",
    total_in_city_category: 10, eligible_count: 4, selection_mode: "ai", cache_hit: false,
    excluded_counts: { date: 6, budget: 0, event_type: 0, duration: 0, language: 0 },
    cards: [
      { id: "DEMO-1", name: "Пример подрядчика 1", categories: ["Ведущий"], city: "Алматы", price_from_kzt: 350000, reason: "Пример объяснения: здесь будет указано, какие особенности профиля отвечают пожеланиям заказчика." },
      { id: "DEMO-2", name: "Пример подрядчика 2", categories: ["Ведущий"], city: "Алматы", price_from_kzt: 500000, reason: "Пример объяснения: здесь будет показано конкретное преимущество кандидата для события." },
      { id: "DEMO-3", name: "Пример подрядчика 3", categories: ["Ведущий"], city: "Алматы", price_from_kzt: 700000, reason: "Пример объяснения: здесь будет указано, чем этот вариант отличается от других." }
    ]
  },
  category_absent: { status: "category_absent", message: "В выбранном городе нет подрядчиков этой категории.", total_in_city_category: 0, eligible_count: 0, excluded_counts: {}, selection_mode: null, cache_hit: false, cards: [] },
  no_matches: { status: "no_matches", message: "Такая категория есть в городе, но никто не прошёл заданные условия.", total_in_city_category: 10, eligible_count: 0, excluded_counts: { date: 0, budget: 10, event_type: 0, duration: 0, language: 0 }, selection_mode: null, cache_hit: false, cards: [] },
  fallback: {
    status: "matched", message: "Подходящие подрядчики найдены. Сейчас показан резервный подбор без AI.",
    total_in_city_category: 2, eligible_count: 1, selection_mode: "fallback", cache_hit: false,
    excluded_counts: { date: 1, budget: 0, event_type: 0, duration: 0, language: 0 },
    cards: [{ id: "DEMO-4", name: "Пример флориста", categories: ["Флорист"], city: "Алматы", price_from_kzt: 200000, reason: "Пример резервного объяснения: кандидат проходит обязательные условия. Конкретные факты появятся с данными API." }]
  }
};

const form = document.querySelector("#recommendation-form");
const scenario = document.querySelector("#demo-scenario");
const result = document.querySelector("#result");
const money = new Intl.NumberFormat("ru-RU");

function node(tag, className, value) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (value !== undefined) item.textContent = String(value);
  return item;
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

function renderCard(card) {
  const article = node("article", "card");
  const top = node("div", "card-top");
  top.append(node("span", "category", (card.categories || []).join(" · ")), node("span", "muted", card.city));
  article.append(top, node("h4", "", card.name), node("p", "card-reason", card.reason));
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

form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  buildRequest(form); // Объект запроса будет отправлен POST /api/recommendations на втором часу.
  renderResponse(examples[scenario.value]);
});
