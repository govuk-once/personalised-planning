import styles from "@/app/page.module.css";

type QuickRepliesProps = {
  options: string[];
  onPick: (option: string, position: number) => void;
};

export default function QuickReplies({ options, onPick }: Readonly<QuickRepliesProps>) {
  return (
    <div role="group" aria-label="Suggested answers" className={styles.quickReplies}>
      {options.map((option, index) => {
        const key = `${index}-${option}`;
        const position = index + 1;

        return (
          <button
            key={key}
            type="button"
            className={styles.quickReply}
            onClick={() => onPick(option, position)}
          >
            {option}
          </button>
        );
      })}
    </div>
  );
}
