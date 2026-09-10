export function saveDescriptionToSessionStorage(item: any) {
  const itemName = "description";

  if(sessionStorage.getItem(itemName)) {
    sessionStorage.clear();
  }
  
  sessionStorage.setItem(itemName, JSON.stringify(item));
}
