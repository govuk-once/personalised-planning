export function GBPCurrencyFormat(number: number) {
  return new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(number)
}
