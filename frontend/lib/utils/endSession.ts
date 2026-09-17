export function endSession(itemsToDelete: Array<string>) {
    itemsToDelete.forEach(item => {
        sessionStorage.removeItem(item)
    })
}
