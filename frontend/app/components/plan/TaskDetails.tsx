import styles from "@/app/page.module.css";
import { GBPCurrencyFormat } from "@/lib/utils/GBPCurrencyFormat";
import type { Task } from "@/lib/types";

// Handles row order + conditional visibility
const rowsFor = (task: Task): Array<[string, string]> =>
  [
    ["How to do it", task.methods.join(", ")],
    ["Where to go", task.location ?? ""],
    ["Deadline", task.deadline ?? ""],
    ["Cost", task.cost > 0 ? GBPCurrencyFormat(task.cost) : ""],
    ["What you'll usually get", task.grant ?? ""],
    ["Department", task.dept],
  ].filter(([, value]) => value) as Array<[string, string]>;

export default function TaskDetails({ task }: Readonly<{ task: Task }>) {
  return (
    <table className={styles.taskTable}>
      <tbody>
        {rowsFor(task).map(([label, value]) => (
          <tr className={styles.tableRow} key={label}>
            <th className={styles.tableHeader} scope="row">
              {label}
            </th>
            <td className={styles.tableCell}>{value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
