"use client"

import styles from "@/app/page.module.css";
import ListCard from "@/app/components/shared/ListCard";
import BackButton from "@/app/components/shared/BackButton";

export default function UserInfo() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <BackButton
          url={"/plan"}
          text={"Back to Plan"}
        />
      </header>
      <main className={styles.main}>
        <div className={styles.intro}>
          <ListCard
            heading={"What you've told us"}
            headingLevel={1}
            editable={true}
            listItems={[
              "You live in England",
              "Both parents will be on the birth certificate",
              "You are employed",
              "At least one parent earns of £60,000",
              "You already have a child"
            ]}
          />
        </div>
      </main>
    </div>
  );
}
