export function saveToSessionStorage(item: any) {
  sessionStorage.setItem("plan", JSON.stringify(item));
}
