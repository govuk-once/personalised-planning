import Link from "next/link";

import styles from "@/app/page.module.css";
import Heading from "@/app/components/shared/Heading";
import Header from "@/app/components/shared/Header";

export default function NoPlan() {
  return (
    <div className={styles.page}>
      <Header
        backButtonUrl={"/"}
        backButtonText={"Home"}
      />
      <main className={styles.main}>
        <div className={styles.intro}>
          <Heading
            heading="No plan yet"
            description="Tell us what is going on first and we will build your plan from that conversation."
          />
          <Link className={styles.ctaLink} href="/">
            Start the conversation
          </Link>
        </div>
      </main>
    </div>
  );
}
