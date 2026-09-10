export function getDescription() {
  let description;

  if(sessionStorage.getItem("description")) {
    description = sessionStorage.getItem("description")
  }
  else if(process.env.MOCK_MODE) {
    description = "Mock description"
  }
  return description;
}
