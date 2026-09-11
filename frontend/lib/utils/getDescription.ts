export function getDescription() {
  let description;

  if(sessionStorage.getItem("description")) {
    description = sessionStorage.getItem("description")
  }
  else if(process.env.MOCK_MODE === "true") {
    description = "Mock description"
  }
  return description;
}
