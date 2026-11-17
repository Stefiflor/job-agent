const res = await fetch("https://www.arbeitnow.com/api/job-board-api");
const json = await res.json();

console.log("Claves de la respuesta:", Object.keys(json));
console.log("Campos de cada oferta:", Object.keys(json.data[0]));
console.log("Ofertas en esta página:", json.data.length);
console.log("---");

for (const j of json.data.slice(0, 10)) {
  console.log(`- ${j.title} | ${j.company_name} | ${j.location} | remote=${j.remote}`);
}
