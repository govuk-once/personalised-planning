import styles from "@/app/page.module.css";

type ComposerProps = {
  draft: string;
  disabled: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
};

export default function Composer({
  draft,
  disabled,
  onChange,
  onSubmit,
}: Readonly<ComposerProps>) {
  return (
    <form
      className={styles.composer}
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <input
        className={styles.composerInput}
        value={draft}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Ask a question..."
        aria-label="Your answer"
        disabled={disabled}
      />
      <button
        className={styles.composerSubmit}
        type="submit"
        disabled={disabled || !draft.trim()}
      >
        Send
      </button>
    </form>
  );
}
