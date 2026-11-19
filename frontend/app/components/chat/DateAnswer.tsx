import { type ChangeEvent, type FormEvent, useId, useState } from "react";

import styles from "@/app/page.module.css";
import { DATE_RANGE, spokenDate } from "@/lib/spoken-date";

type DateAnswerProps = {
  onPick: (date: string) => void;
};

export default function DateAnswer({ onPick }: Readonly<DateAnswerProps>) {
  const id = useId();
  const [value, setValue] = useState("");

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const spoken = spokenDate(value);

    if (spoken) {
      onPick(spoken);
    }
  }

  function changed(event: ChangeEvent<HTMLInputElement>) {
    setValue(event.target.value);
  }

  return (
    <form className={styles.dateAnswer} onSubmit={submit}>
      <label htmlFor={id} className={styles.dateAnswerLabel}>
        Choose a date
      </label>
      <input
        id={id}
        type="date"
        className={styles.dateAnswerInput}
        required
        min={DATE_RANGE.min}
        max={DATE_RANGE.max}
        value={value}
        onChange={changed}
      />
      <button type="submit" className={styles.dateAnswerSubmit}>
        Use this date
      </button>
    </form>
  );
}
