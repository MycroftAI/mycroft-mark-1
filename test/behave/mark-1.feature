Feature: mycroft-mark-1

  Scenario: Set eye color
    Given an english speaking user
     When the user says "Set eye color to blue"
     Then "mycroft-mark-1" should reply with dialog from "set.color.success.dialog"
